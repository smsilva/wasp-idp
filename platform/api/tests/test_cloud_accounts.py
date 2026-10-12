"""Cloud accounts (ADR 0029, #193)."""
import json

import pytest
from fastapi.testclient import TestClient

from platform_api.app import create_app
from platform_api.cloud_accounts import CLOUD_ACCOUNTS, VERIFY_ANNOTATION
from platform_api.journal import Journal
from fakes import FakeState
from tokens import TokenFactory

ROLE = "arn:aws:iam::123456789012:role/platform"
BASE = "arn:aws:iam::210987654321:user/platform-base"


class FakeBaseIdentity:
  def __init__(self, arn=BASE):
    self.value = arn

  def arn(self):
    return self.value


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
def base():
  return FakeBaseIdentity()


@pytest.fixture
def client(state, journal_path, tokens, base):
  return TestClient(create_app(state, Journal(journal_path), tokens.verifier(), base_identity=base))


@pytest.fixture
def as_(tokens):
  people = {
    "owner": dict(sub="owner-1", email="owner@example.com", group_paths=["/platform-users"]),
    "other": dict(sub="other-1", email="other@example.com", group_paths=["/platform-users"]),
    "admin": dict(sub="admin-1", email="admin@example.com", group_paths=["/platform-admins", "/platform-users"]),
  }
  return lambda who: {"Authorization": f"Bearer {tokens.issue(**people[who])}"}


def add(client, as_, name="nonprod-aws", role=ROLE, who="owner", **extra):
  return client.post("/v1/cloud/accounts", json={"name": name, "vendor": "aws", "roleArn": role, **extra}, headers=as_(who))


def test_add_returns_the_trust_policy(client, as_, state):
  response = add(client, as_, regions=["us-east-1", "sa-east-1"])
  assert response.status_code == 202
  body = response.json()
  assert body["status"] == "pending"
  assert body["accountId"] == "123456789012"
  assert body["regions"] == ["sa-east-1", "us-east-1"]
  spec = state.stores[CLOUD_ACCOUNTS]["nonprod-aws"]["spec"]
  statement = body["trustPolicy"]["Statement"][0]
  assert statement["Principal"] == {"AWS": BASE}
  assert statement["Action"] == "sts:AssumeRole"
  assert statement["Condition"] == {"StringEquals": {"sts:ExternalId": spec["aws"]["externalId"]}}
  assert len(spec["aws"]["externalId"]) >= 32
  assert state.stores[CLOUD_ACCOUNTS]["nonprod-aws"]["metadata"]["annotations"]["platform.wasp.silvios.me/owner"] == "owner-1"


def test_external_id_comes_from_the_api(client, as_, state):
  response = add(client, as_, externalId="chosen-by-me")
  assert response.status_code == 202
  assert state.stores[CLOUD_ACCOUNTS]["nonprod-aws"]["spec"]["aws"]["externalId"] != "chosen-by-me"
  other = add(client, as_, name="second", role="arn:aws:iam::123456789012:role/other").json()
  first = client.get("/v1/cloud/accounts/nonprod-aws", headers=as_("owner")).json()
  assert other["trustPolicy"] != first["trustPolicy"]


def test_external_id_stays_out_of_the_journal(client, as_, state, journal_path):
  add(client, as_)
  external_id = state.stores[CLOUD_ACCOUNTS]["nonprod-aws"]["spec"]["aws"]["externalId"]
  assert external_id not in journal_path.read_text()
  entries = [json.loads(line) for line in journal_path.read_text().splitlines()]
  assert entries[0]["spec"] == {"vendor": "aws", "aws": {"roleArn": ROLE, "regions": []}}


def test_without_base_credential(state, journal_path, tokens, as_):
  client = TestClient(create_app(state, Journal(journal_path), tokens.verifier(), base_identity=FakeBaseIdentity(None)))
  response = add(client, as_)
  assert response.status_code == 409
  assert "--aws-profile" in response.json()["error"]["message"]
  bare = TestClient(create_app(state, Journal(journal_path), tokens.verifier()))
  assert add(bare, as_).status_code == 409




@pytest.mark.parametrize("field,value", [
  ("roleArn", "arn:aws:iam::123:role/platform"),
  ("roleArn", "arn:aws:iam::123456789012:user/someone"),
  ("roleArn", "arn:aws:iam::123456789012:role/platform\n"),
  ("vendor", "azure"),
  ("name", "Nonprod"),
  ("regions", ["moon-1"]),
])
def test_invalid_requests(client, as_, field, value):
  body = {"name": "nonprod-aws", "vendor": "aws", "roleArn": ROLE, field: value}
  assert client.post("/v1/cloud/accounts", json=body, headers=as_("owner")).status_code == 422


def test_role_path_is_accepted(client, as_):
  assert add(client, as_, role="arn:aws:iam::123456789012:role/platform/team-a/deployer").status_code == 202


def test_same_role_twice_is_a_conflict(client, as_):
  add(client, as_)
  response = add(client, as_, name="again", who="other")
  assert response.status_code == 409
  assert "already registered" in response.json()["error"]["message"]
  assert add(client, as_, role="arn:aws:iam::123456789012:role/other").status_code == 409


def test_others_neither_see_nor_remove(client, as_, state):
  add(client, as_)
  assert client.get("/v1/cloud/accounts", headers=as_("other")).json()["items"] == []
  assert client.get("/v1/cloud/accounts/nonprod-aws", headers=as_("other")).status_code == 403
  assert client.post("/v1/cloud/accounts/nonprod-aws/verify", headers=as_("other")).status_code == 403
  assert client.delete("/v1/cloud/accounts/nonprod-aws", headers=as_("other")).status_code == 403
  assert "nonprod-aws" in state.stores[CLOUD_ACCOUNTS]


def test_admin_sees_and_removes_everyone(client, as_, state):
  add(client, as_)
  items = client.get("/v1/cloud/accounts", headers=as_("admin")).json()["items"]
  assert [(item["name"], item["owner"]) for item in items] == [("nonprod-aws", "owner@example.com")]
  assert "trustPolicy" not in items[0]
  assert client.delete("/v1/cloud/accounts/nonprod-aws", headers=as_("admin")).status_code == 202
  assert "nonprod-aws" not in state.stores[CLOUD_ACCOUNTS]


def test_verify_marks_a_pending_validation(client, as_, state, journal_path):
  add(client, as_)
  obj = state.stores[CLOUD_ACCOUNTS]["nonprod-aws"]
  obj["status"] = {"accountId": "123456789012", "conditions": [{"type": "Ready", "status": "False", "reason": "TrustNotEstablished", "message": "AccessDenied"}]}
  response = client.post("/v1/cloud/accounts/nonprod-aws/verify", headers=as_("owner"))
  assert response.status_code == 202
  assert response.json()["verifyPending"] is True
  assert response.json()["status"] == "TrustNotEstablished"
  requested = state.stores[CLOUD_ACCOUNTS]["nonprod-aws"]["metadata"]["annotations"][VERIFY_ANNOTATION]
  # The controller answers by echoing the annotation it validated.
  state.stores[CLOUD_ACCOUNTS]["nonprod-aws"]["status"] = {
    "accountId": "123456789012", "callerArn": "arn:aws:sts::123456789012:assumed-role/platform/platform-verify-nonprod-aws",
    "lastValidated": "2026-10-11T12:00:00Z", "observedVerifyRequest": requested,
    "conditions": [{"type": "Ready", "status": "True", "reason": "Verified", "message": "trust verified"}],
  }
  account = client.get("/v1/cloud/accounts/nonprod-aws", headers=as_("owner")).json()
  assert (account["status"], account["verifyPending"]) == ("ready", False)
  actions = [json.loads(line).get("action") for line in journal_path.read_text().splitlines()]
  assert [action for action in actions if action] == ["create", "verify"]


def test_unknown_account(client, as_):
  assert client.get("/v1/cloud/accounts/missing", headers=as_("owner")).status_code == 404
  assert client.delete("/v1/cloud/accounts/missing", headers=as_("owner")).status_code == 404
  assert client.post("/v1/cloud/accounts/missing/verify", headers=as_("owner")).status_code == 404


def test_name_taken(client, as_):
  add(client, as_)
  assert add(client, as_, role="arn:aws:iam::123456789012:role/other").status_code == 409


@pytest.mark.parametrize("role", [
  "arn:aws:iam::123456789012:role/Platform",
  "arn:aws:iam::123456789012:role/team-a/platform",
])
def test_same_role_in_another_spelling_is_a_conflict(client, as_, role):
  add(client, as_)
  assert add(client, as_, name="again", role=role, who="other").status_code == 409


def test_concurrent_create_of_the_same_role_steps_back(client, as_, state):
  def racer(obj):
    if obj["metadata"]["name"] == "nonprod-aws":
      state.stores[CLOUD_ACCOUNTS]["racer"] = {"metadata": {"name": "racer", "uid": "uid-racer"}, "spec": {"vendor": "aws", "aws": {"roleArn": ROLE}}}

  state.on_create = racer
  response = add(client, as_)
  assert response.status_code == 409
  assert sorted(state.stores[CLOUD_ACCOUNTS]) == ["racer"]
