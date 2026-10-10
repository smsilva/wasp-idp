import json
import re

import pytest
from fastapi.testclient import TestClient

from platform_api.app import create_app
from platform_api.journal import Journal
from tokens import ISSUER, TokenFactory
from platform_api.state import AlreadyExists, Conflict, NotFound


class FakeState:
  def __init__(self):
    self.objects = {}
    self.version = 0
    self.on_create = None

  def _bump(self, obj):
    self.version += 1
    obj["metadata"]["resourceVersion"] = str(self.version)

  def create(self, plural, body):
    name = body["metadata"]["name"]
    if name in self.objects:
      raise AlreadyExists(name)
    obj = json.loads(json.dumps(body))
    obj["metadata"]["creationTimestamp"] = "2026-10-10T00:00:00Z"
    self._bump(obj)
    self.objects[name] = obj
    created = json.loads(json.dumps(obj))
    if self.on_create:
      self.on_create(obj)
    return created

  def replace_status(self, plural, body):
    name = body["metadata"]["name"]
    current = self.objects[name]
    if current["metadata"]["resourceVersion"] != body["metadata"]["resourceVersion"]:
      raise Conflict(name)
    current["status"] = body["status"]
    self._bump(current)
    return json.loads(json.dumps(current))

  def delete(self, plural, name):
    if name not in self.objects:
      raise NotFound(name)
    del self.objects[name]

  def get(self, plural, name):
    if name not in self.objects:
      raise NotFound(name)
    return json.loads(json.dumps(self.objects[name]))

  def list(self, plural):
    return [json.loads(json.dumps(obj)) for obj in self.objects.values()]


@pytest.fixture
def state():
  return FakeState()


@pytest.fixture
def journal_path(tmp_path):
  return tmp_path / "journal.jsonl"


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def client(state, journal_path, tokens):
  client = TestClient(create_app(state, Journal(journal_path), tokens.verifier()))
  client.headers["Authorization"] = f"Bearer {tokens.issue()}"
  return client


def test_healthz(client):
  assert client.get("/healthz").json() == {"status": "ok"}


def test_create_without_provider_reports_condition(client, state):
  response = client.post("/v1/environments", json={"name": "greetings-test", "profile": "ephemeral", "expires": "3d"})
  assert response.status_code == 202
  body = response.json()
  assert body["status"] == "NoProviderForCapability"
  assert re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$", body["expiresAt"])
  ready = state.objects["greetings-test"]["status"]["conditions"][0]
  assert (ready["type"], ready["status"], ready["reason"]) == ("Ready", "False", "NoProviderForCapability")


def test_create_keeps_status_written_by_provider(client, state):
  def provider_claims(obj):
    obj["status"] = {"conditions": [{"type": "Ready", "status": "False", "reason": "Provisioning"}]}
    state._bump(obj)

  state.on_create = provider_claims
  response = client.post("/v1/environments", json={"name": "fast", "profile": "ephemeral"})
  assert response.json()["status"] == "Provisioning"


def test_create_duplicate_is_conflict(client):
  payload = {"name": "dup", "profile": "shared"}
  assert client.post("/v1/environments", json=payload).status_code == 202
  assert client.post("/v1/environments", json=payload).status_code == 409


@pytest.mark.parametrize("payload", [
  {"name": "Bad_Name", "profile": "ephemeral"},
  {"name": "a" * 29, "profile": "ephemeral"},
  {"name": "ok", "profile": "production"},
  {"name": "ok", "profile": "ephemeral", "expires": "3 days"},
])
def test_create_rejects_invalid_input(client, payload):
  assert client.post("/v1/environments", json=payload).status_code == 422


def test_list_and_get(client):
  client.post("/v1/environments", json={"name": "b-env", "profile": "shared"})
  client.post("/v1/environments", json={"name": "a-env", "profile": "ephemeral", "expires": "1h"})
  items = client.get("/v1/environments").json()["items"]
  assert [item["name"] for item in items] == ["a-env", "b-env"]
  assert client.get("/v1/environments/a-env").json()["profile"] == "ephemeral"
  assert client.get("/v1/environments/missing").status_code == 404


def test_delete(client, state):
  client.post("/v1/environments", json={"name": "gone", "profile": "ephemeral"})
  assert client.delete("/v1/environments/gone").status_code == 202
  assert "gone" not in state.objects
  assert client.delete("/v1/environments/gone").status_code == 404


def test_journal_records_before_and_after_apply(client, journal_path):
  client.post("/v1/environments", json={"name": "audited", "profile": "ephemeral"})
  client.delete("/v1/environments/audited")
  lines = [json.loads(line) for line in journal_path.read_text().splitlines()]
  assert [line["applied"] for line in lines] == [False, True, False, True]
  assert lines[0]["action"] == "create" and lines[0]["spec"] == {"profile": "ephemeral"}
  assert lines[0]["id"] == lines[1]["id"]
  assert lines[2]["action"] == "delete"
  assert lines[0]["actor"] == "user-1 (dev@example.com)"


def test_journal_keeps_unapplied_request_when_apply_fails(client, journal_path):
  client.post("/v1/environments", json={"name": "dup", "profile": "ephemeral"})
  client.post("/v1/environments", json={"name": "dup", "profile": "ephemeral"})
  lines = [json.loads(line) for line in journal_path.read_text().splitlines()]
  assert [line["applied"] for line in lines] == [False, True, False]


@pytest.mark.parametrize("host,status", [("127.0.0.1:9090", 200), ("localhost:9090", 200), ("attacker.example:9090", 400)])
def test_rejects_unexpected_host_header(state, journal_path, tokens, host, status):
  client = TestClient(create_app(state, Journal(journal_path), tokens.verifier(), ["127.0.0.1", "localhost"]))
  headers = {"Host": host, "Authorization": f"Bearer {tokens.issue()}"}
  assert client.get("/v1/environments", headers=headers).status_code == status


def ready_with_kubeconfig(state, name):
  state.objects[name]["status"] = {"port": 7100, "kubeconfigData": "apiVersion: v1\n", "conditions": [{"type": "Ready", "status": "True"}]}


def test_create_records_owner(client, state):
  client.post("/v1/environments", json={"name": "mine", "profile": "ephemeral"})
  assert state.objects["mine"]["metadata"]["annotations"]["platform.wasp.silvios.me/owner"] == "user-1"


def test_kubeconfig_data_only_on_single_get_for_owner(client, state):
  client.post("/v1/environments", json={"name": "vc", "profile": "ephemeral"})
  ready_with_kubeconfig(state, "vc")
  assert "kubeconfigData" not in client.get("/v1/environments").json()["items"][0]
  single = client.get("/v1/environments/vc").json()
  assert single["kubeconfigData"] == "apiVersion: v1\n" and single["port"] == 7100


def test_kubeconfig_hidden_from_other_users(client, state, tokens):
  client.post("/v1/environments", json={"name": "vc", "profile": "ephemeral"})
  ready_with_kubeconfig(state, "vc")
  other = {"Authorization": f"Bearer {tokens.issue(sub='user-2', email='other@example.com')}"}
  single = client.get("/v1/environments/vc", headers=other).json()
  assert "kubeconfigData" not in single and single["status"] == "ready"


def test_kubeconfig_visible_to_platform_admins(client, state, tokens):
  client.post("/v1/environments", json={"name": "vc", "profile": "ephemeral"})
  ready_with_kubeconfig(state, "vc")
  admin = {"Authorization": f"Bearer {tokens.issue(sub='admin-1', groups=['platform-admins'])}"}
  assert client.get("/v1/environments/vc", headers=admin).json()["kubeconfigData"] == "apiVersion: v1\n"
