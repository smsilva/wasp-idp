"""OCI registries (ADR 0037, #365): platform-admins register them, anyone signed in reads them."""
import json

import pytest
from fastapi.testclient import TestClient

from fakes import FakeState
from platform_api.app import create_app
from platform_api.journal import Journal
from tokens import TokenFactory


@pytest.fixture
def state():
  state = FakeState()
  state.create("scmconnections", {"metadata": {"name": "wasp-foundry"}, "spec": {"vendor": "github", "github": {"org": "Wasp-Foundry"}}})
  return state


@pytest.fixture
def journal_path(tmp_path):
  return tmp_path / "journal.jsonl"


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def client(state, journal_path, tokens):
  return TestClient(create_app(state, Journal(journal_path), tokens.verifier()))


@pytest.fixture
def admin(tokens):
  return {"Authorization": f"Bearer {tokens.issue(sub='admin-1', group_paths=['/platform-admins', '/platform-users'])}"}


@pytest.fixture
def user(tokens):
  return {"Authorization": f"Bearer {tokens.issue(sub='user-1', group_paths=['/platform-users'])}"}


def test_add_from_the_scm_connection(client, state, admin, journal_path):
  response = client.post("/v1/registries", json={"name": "ghcr-wasp-foundry", "scmConnection": "wasp-foundry", "default": True}, headers=admin)
  assert response.status_code == 201, response.text
  view = response.json()
  assert (view["vendor"], view["address"], view["default"], view["pullMode"], view["status"]) == ("ghcr", "ghcr.io/wasp-foundry", True, "anonymous", "pending")
  # Filled once: the registry keeps no reference to the connection.
  assert state.get("ociregistries", "ghcr-wasp-foundry")["spec"] == {"vendor": "ghcr", "host": "ghcr.io", "namespace": "wasp-foundry", "default": True, "pull": {"mode": "anonymous"}}
  entry = json.loads(journal_path.read_text().splitlines()[0])
  assert (entry["action"], entry["kind"], entry["name"]) == ("create", "OCIRegistry", "ghcr-wasp-foundry")


def test_add_explicit_and_read_as_anyone(client, admin, user):
  assert client.post("/v1/registries", json={"name": "ghcr-smsilva", "vendor": "ghcr", "namespace": "smsilva"}, headers=admin).status_code == 201
  items = client.get("/v1/registries", headers=user).json()["items"]
  assert [(item["name"], item["address"], item["default"]) for item in items] == [("ghcr-smsilva", "ghcr.io/smsilva", False)]
  assert client.get("/v1/registries/ghcr-smsilva", headers=user).json()["host"] == "ghcr.io"
  assert client.get("/v1/registries/nowhere", headers=user).status_code == 404


@pytest.mark.parametrize("body,message", [
  ({"name": "x", "vendor": "harbor", "namespace": "lab"}, "supported vendors: ghcr"),
  ({"name": "x", "vendor": "ghcr", "host": "registry.example.com", "namespace": "acme"}, "a ghcr registry is ghcr.io"),
  ({"name": "x", "vendor": "ghcr"}, "vendor and namespace are required"),
  ({"name": "x", "scmConnection": "wasp-foundry", "namespace": "acme"}, "either scmConnection or vendor"),
  ({"name": "X_bad", "vendor": "ghcr", "namespace": "acme"}, "lowercase"),
  ({"name": "x", "vendor": "ghcr", "namespace": "a/b"}, "lowercase letters"),
])
def test_add_refusals(client, state, admin, body, message):
  response = client.post("/v1/registries", json=body, headers=admin)
  assert response.status_code == 422
  assert message in response.text
  assert state.list("ociregistries") == []


def test_unknown_or_non_github_connection(client, state, admin):
  assert "scm connection 'nope' not found" in client.post("/v1/registries", json={"name": "x", "scmConnection": "nope"}, headers=admin).text
  state.create("scmconnections", {"metadata": {"name": "bad"}, "spec": {"vendor": "github"}})
  assert "is not a github connection with an org" in client.post("/v1/registries", json={"name": "x", "scmConnection": "bad"}, headers=admin).text


def test_name_and_address_are_unique(client, admin):
  client.post("/v1/registries", json={"name": "ghcr-wasp-foundry", "scmConnection": "wasp-foundry"}, headers=admin)
  again = client.post("/v1/registries", json={"name": "ghcr-wasp-foundry", "vendor": "ghcr", "namespace": "other"}, headers=admin)
  assert again.status_code == 409 and "already exists" in again.text
  same = client.post("/v1/registries", json={"name": "another", "vendor": "ghcr", "namespace": "wasp-foundry"}, headers=admin)
  assert same.status_code == 409 and "ghcr.io/wasp-foundry is already registry 'ghcr-wasp-foundry'" in same.text


def test_only_admins_write(client, user):
  for response in (
    client.post("/v1/registries", json={"name": "x", "vendor": "ghcr", "namespace": "acme"}, headers=user),
    client.put("/v1/registries/x/default", headers=user),
    client.delete("/v1/registries/x", headers=user),
  ):
    assert response.status_code == 403
    assert "requires group 'platform-admins'" in response.text


def test_at_most_one_default(client, state, admin):
  client.post("/v1/registries", json={"name": "a", "vendor": "ghcr", "namespace": "a", "default": True}, headers=admin)
  client.post("/v1/registries", json={"name": "b", "vendor": "ghcr", "namespace": "b", "default": True}, headers=admin)
  assert [obj["metadata"]["name"] for obj in state.list("ociregistries") if obj["spec"]["default"]] == ["b"]
  assert client.put("/v1/registries/a/default", headers=admin).json()["default"] is True
  assert [obj["metadata"]["name"] for obj in state.list("ociregistries") if obj["spec"]["default"]] == ["a"]
  assert client.put("/v1/registries/nope/default", headers=admin).status_code == 404


def test_delete_refused_while_versions_name_it(client, state, admin):
  client.post("/v1/registries", json={"name": "ghcr-wasp-foundry", "scmConnection": "wasp-foundry"}, headers=admin)
  state.create("versions", {"metadata": {"name": "hello-api.0.1.0"}, "spec": {"component": "hello-api", "registry": "ghcr-wasp-foundry"}})
  response = client.delete("/v1/registries/ghcr-wasp-foundry", headers=admin)
  assert response.status_code == 409
  assert "holds 1 version(s) of the index (hello-api.0.1.0): it stays" in response.text
  state.delete("versions", "hello-api.0.1.0")
  assert client.delete("/v1/registries/ghcr-wasp-foundry", headers=admin).status_code == 202
  assert state.list("ociregistries") == []
  assert client.delete("/v1/registries/ghcr-wasp-foundry", headers=admin).status_code == 404


def test_status_from_the_controller(client, state, admin, user):
  client.post("/v1/registries", json={"name": "ghcr-wasp-foundry", "scmConnection": "wasp-foundry"}, headers=admin)
  state.stores["ociregistries"]["ghcr-wasp-foundry"]["status"] = {"conditions": [{"type": "Ready", "status": "False", "reason": "Unreachable", "message": "https://ghcr.io/v2/: timed out"}]}
  view = client.get("/v1/registries/ghcr-wasp-foundry", headers=user).json()
  assert (view["status"], view["message"]) == ("Unreachable", "https://ghcr.io/v2/: timed out")
