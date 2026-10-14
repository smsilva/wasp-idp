"""Cloud accounts (ADR 0029, #193)."""
import json

import pytest
from fastapi.testclient import TestClient

from platform_api.app import create_app
from platform_api.cloud_accounts import CLOUD_ACCOUNTS, VERIFY_ANNOTATION
from platform_api.journal import Journal
from platform_api.state import ENVIRONMENTS
from platform_api.teams import users_of
from fakes import FakeState, FakeTeams
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
  return TestClient(create_app(state, Journal(journal_path), tokens.verifier(), base_identity=base, teams=FakeTeams("team-alpha", "team-beta")))


@pytest.fixture
def as_(tokens):
  people = {
    "owner": dict(sub="owner-1", email="owner@example.com", group_paths=["/platform-users", "/teams/team-alpha"]),
    "member": dict(sub="member-1", email="member@example.com", group_paths=["/platform-users", "/teams/team-alpha"]),
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


def share(client, as_, team="team-alpha", who="owner", name="nonprod-aws"):
  return client.put(f"/v1/cloud/accounts/{name}/shares/{team}", headers=as_(who))


def test_a_team_member_sees_a_shared_account_without_the_trust_policy(client, as_):
  add(client, as_)
  assert client.get("/v1/cloud/accounts/nonprod-aws", headers=as_("member")).status_code == 403
  response = share(client, as_)
  assert response.status_code == 200
  assert response.json()["sharedWith"] == ["team-alpha"]
  assert "trustPolicy" in response.json()
  items = client.get("/v1/cloud/accounts", headers=as_("member")).json()["items"]
  assert [(item["name"], item["sharedWith"]) for item in items] == [("nonprod-aws", ["team-alpha"])]
  account = client.get("/v1/cloud/accounts/nonprod-aws", headers=as_("member")).json()
  assert account["owner"] == "owner@example.com"
  assert "trustPolicy" not in account
  assert "externalId" not in json.dumps(account)
  assert "trustPolicy" in client.get("/v1/cloud/accounts/nonprod-aws", headers=as_("owner")).json()
  assert client.get("/v1/cloud/accounts", headers=as_("other")).json()["items"] == []


def test_a_team_member_neither_verifies_removes_nor_shares(client, as_, state):
  add(client, as_)
  share(client, as_)
  assert client.post("/v1/cloud/accounts/nonprod-aws/verify", headers=as_("member")).status_code == 403
  assert client.delete("/v1/cloud/accounts/nonprod-aws", headers=as_("member")).status_code == 403
  assert share(client, as_, team="team-beta", who="member").status_code == 403
  assert client.delete("/v1/cloud/accounts/nonprod-aws/shares/team-alpha", headers=as_("member")).status_code == 403
  assert "nonprod-aws" in state.stores[CLOUD_ACCOUNTS]


def test_the_owner_shares_only_with_their_own_teams(client, as_):
  add(client, as_)
  response = share(client, as_, team="team-beta")
  assert response.status_code == 403
  assert "team-beta" in response.json()["error"]["message"]
  assert share(client, as_, team="team-beta", who="admin").status_code == 200
  assert share(client, as_, team="team-missing", who="admin").status_code == 422
  assert share(client, as_, team="Not_A_Team", who="admin").status_code == 422


def test_sharing_twice_is_a_no_op(client, as_):
  add(client, as_)
  share(client, as_)
  assert share(client, as_).json()["sharedWith"] == ["team-alpha"]


def test_unshare_takes_access_away(client, as_, state, journal_path):
  add(client, as_)
  share(client, as_)
  response = client.delete("/v1/cloud/accounts/nonprod-aws/shares/team-alpha", headers=as_("owner"))
  assert response.status_code == 200
  assert response.json()["sharedWith"] == []
  assert "sharedWith" not in state.stores[CLOUD_ACCOUNTS]["nonprod-aws"]["spec"]
  assert client.get("/v1/cloud/accounts/nonprod-aws", headers=as_("member")).status_code == 403
  assert client.delete("/v1/cloud/accounts/nonprod-aws/shares/team-alpha", headers=as_("owner")).status_code == 404
  records = [json.loads(line) for line in journal_path.read_text().splitlines()]
  assert [(r["action"], r["spec"]) for r in records if r.get("action") in ("share", "unshare")] == [("share", {"team": "team-alpha"}), ("unshare", {"team": "team-alpha"})]


def test_share_of_an_unknown_account(client, as_):
  assert share(client, as_, name="missing").status_code == 404


def test_a_team_sharing_an_account_is_in_use(client, as_, state):
  add(client, as_)
  share(client, as_)
  assert users_of(state, "team-alpha") == ["cloudaccount/nonprod-aws"]


# An environment in a cloud account (#435).

def ready(state, name="nonprod-aws", regions=("us-east-1",)):
  """A usable account: verified, with the region its environments go to (#436)."""
  obj = state.stores[CLOUD_ACCOUNTS][name]
  obj["spec"]["aws"]["regions"] = list(regions)
  obj["status"] = {"conditions": [{"type": "Ready", "status": "True", "reason": "TrustEstablished"}]}


def create_environment(client, as_, name="cloud-env", account="nonprod-aws", who="owner"):
  return client.post("/v1/environments", json={"name": name, "profile": "ephemeral", "cloudAccount": account}, headers=as_(who))


def test_an_environment_in_a_ready_account(client, as_, state, journal_path):
  add(client, as_)
  ready(state)
  response = create_environment(client, as_)
  assert response.status_code == 202
  assert response.json()["cloudAccount"] == "nonprod-aws"
  assert response.json()["status"] == "NoProviderForCapability"
  assert state.stores[ENVIRONMENTS]["cloud-env"]["spec"]["cloudAccount"] == "nonprod-aws"
  # The exact account authorized, for the provider to check (#436).
  annotations = state.stores[ENVIRONMENTS]["cloud-env"]["metadata"]["annotations"]
  assert annotations["platform.wasp.silvios.me/cloud-account-uid"] == state.stores[CLOUD_ACCOUNTS]["nonprod-aws"]["metadata"]["uid"]
  records = [json.loads(line) for line in journal_path.read_text().splitlines()]
  assert [r["spec"]["cloudAccount"] for r in records if r.get("kind") == "Environment"] == ["nonprod-aws"]
  items = client.get("/v1/environments", headers=as_("owner")).json()["items"]
  assert [(item["name"], item["cloudAccount"]) for item in items] == [("cloud-env", "nonprod-aws")]


def test_an_environment_without_account_shows_none(client, as_):
  response = client.post("/v1/environments", json={"name": "local-env", "profile": "ephemeral"}, headers=as_("owner"))
  assert response.status_code == 202
  assert response.json()["cloudAccount"] is None


def test_the_account_must_exist_and_be_ready(client, as_, state):
  response = create_environment(client, as_, account="missing")
  assert response.status_code == 422
  assert "cloud account 'missing' not found" in response.json()["error"]["message"]
  add(client, as_)
  response = create_environment(client, as_)
  assert response.status_code == 422
  assert "is not ready" in response.json()["error"]["message"]
  assert create_environment(client, as_, account="Not_An_Account").status_code == 422
  assert ENVIRONMENTS not in state.stores or state.stores[ENVIRONMENTS] == {}


def test_the_account_must_have_a_region(client, as_, state):
  add(client, as_)
  ready(state, regions=())
  response = create_environment(client, as_)
  assert response.status_code == 422
  assert "has no region" in response.json()["error"]["message"]
  assert ENVIRONMENTS not in state.stores or state.stores[ENVIRONMENTS] == {}


def test_only_who_uses_the_account_creates_in_it(client, as_, state):
  add(client, as_)
  ready(state)
  response = create_environment(client, as_, who="member")
  assert response.status_code == 403
  assert "cloud account 'nonprod-aws'" in response.json()["error"]["message"]
  share(client, as_)
  assert create_environment(client, as_, who="member").status_code == 202
  assert create_environment(client, as_, name="by-admin", who="admin").status_code == 202
  assert create_environment(client, as_, name="by-other", who="other").status_code == 403


def test_unshare_keeps_the_environments_already_created(client, as_, state):
  add(client, as_)
  ready(state)
  share(client, as_)
  create_environment(client, as_, who="member")
  client.delete("/v1/cloud/accounts/nonprod-aws/shares/team-alpha", headers=as_("owner"))
  assert "cloud-env" in state.stores[ENVIRONMENTS]
  assert client.get("/v1/environments/cloud-env", headers=as_("member")).status_code == 200


def test_an_account_in_use_is_not_removed(client, as_, state):
  add(client, as_)
  ready(state)
  create_environment(client, as_)
  response = client.delete("/v1/cloud/accounts/nonprod-aws", headers=as_("owner"))
  assert response.status_code == 409
  assert "cloud-env" in response.json()["error"]["message"]
  assert "nonprod-aws" in state.stores[CLOUD_ACCOUNTS]
  del state.stores[ENVIRONMENTS]["cloud-env"]
  assert client.delete("/v1/cloud/accounts/nonprod-aws", headers=as_("owner")).status_code == 202


def test_an_environment_in_an_account_has_no_vcluster(client, as_, state):
  add(client, as_)
  ready(state)
  create_environment(client, as_, who="admin")
  # Even with a kubeconfig in the status, the routes of a vcluster never answer for it.
  state.stores[ENVIRONMENTS]["cloud-env"]["status"]["kubeconfigData"] = "apiVersion: v1"
  for response in (
    client.post("/v1/environments/cloud-env/credentials", headers=as_("admin")),
    client.get("/v1/environments/cloud-env/admin-kubeconfig", headers=as_("admin")),
  ):
    assert response.status_code == 409
    assert "has no vcluster" in response.json()["error"]["message"]
  assert "kubeconfigData" not in client.get("/v1/environments/cloud-env", headers=as_("admin")).json()


def test_an_environment_in_an_account_shows_what_it_has_there(client, as_, state):
  add(client, as_)
  ready(state)
  create_environment(client, as_)
  assert client.get("/v1/environments/cloud-env", headers=as_("owner")).json()["cloud"] is None
  # Written by the crossplane_aws provider (#436).
  state.stores[ENVIRONMENTS]["cloud-env"]["status"]["cloud"] = {"vendor": "aws", "region": "us-east-1", "vpcId": "vpc-0abc"}
  body = client.get("/v1/environments/cloud-env", headers=as_("owner")).json()
  assert body["cloud"] == {"vendor": "aws", "region": "us-east-1", "vpcId": "vpc-0abc"}
