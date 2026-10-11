"""Personal environment credentials (ADR 0028, #233)."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from platform_api.app import create_app
from platform_api.credentials import NAMESPACE, TOKEN_SECONDS, VclusterCredentials, identity_name
from platform_api.journal import Journal
from fakes import ADMIN_KUBECONFIG, FakeCredentials, FakeState, FakeTeams
from tokens import TokenFactory


@pytest.fixture
def state():
  return FakeState()


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def credentials():
  return FakeCredentials()


@pytest.fixture
def client(state, tmp_path, tokens, credentials):
  return TestClient(create_app(state, Journal(tmp_path / "journal.jsonl"), tokens.verifier(), teams=FakeTeams("team-alpha"), credentials=credentials))


@pytest.fixture
def as_(tokens):
  people = {
    "owner": dict(sub="owner-1", email="owner@example.com", group_paths=["/platform-users", "/teams/team-alpha"]),
    "teammate": dict(sub="mate-1", email="mate@example.com", group_paths=["/platform-users", "/teams/team-alpha"]),
    "outsider": dict(sub="out-1", email="out@example.com", group_paths=["/platform-users"]),
    "admin": dict(sub="admin-1", email="admin@example.com", group_paths=["/platform-admins", "/platform-users"]),
  }
  return lambda who: {"Authorization": f"Bearer {tokens.issue(**people[who])}"}


def environment(client, as_, state, ready=True, **extra):
  client.post("/v1/environments", json={"name": "vc", "profile": "ephemeral", **extra}, headers=as_("owner"))
  if ready:
    state.objects["vc"]["status"] = {"port": 7100, "kubeconfigData": ADMIN_KUBECONFIG, "conditions": [{"type": "Ready", "status": "True"}]}


def issue(client, as_, who):
  return client.post("/v1/environments/vc/credentials", headers=as_(who))


def test_owner_and_teammate_get_their_own_token(client, as_, state, credentials):
  environment(client, as_, state, sharedWith=["team-alpha"])
  assert issue(client, as_, "owner").json() == {"token": "token-of-owner-1", "expirationTimestamp": "2026-10-11T12:10:00Z"}
  assert issue(client, as_, "teammate").json()["token"] == "token-of-mate-1"
  assert credentials.identities["vc"] == {"owner-1", "mate-1"}


def test_outsider_gets_no_token(client, as_, state, credentials):
  environment(client, as_, state)
  assert issue(client, as_, "outsider").status_code == 403
  assert "vc" not in credentials.identities


def test_unknown_and_not_ready_environments(client, as_, state):
  assert issue(client, as_, "owner").status_code == 404
  environment(client, as_, state, ready=False)
  assert issue(client, as_, "owner").status_code == 409


def test_vcluster_down_is_unavailable(client, as_, state, credentials):
  environment(client, as_, state)
  credentials.down = True
  response = issue(client, as_, "owner")
  assert response.status_code == 503
  assert response.json()["error"]["code"] == "unavailable"


def test_without_credentials_configured(state, tmp_path, tokens, as_):
  client = TestClient(create_app(state, Journal(tmp_path / "journal.jsonl"), tokens.verifier()))
  environment(client, as_, state)
  assert issue(client, as_, "owner").status_code == 503


def test_admin_kubeconfig_is_for_admins_only(client, as_, state):
  environment(client, as_, state)
  assert client.get("/v1/environments/vc/admin-kubeconfig", headers=as_("owner")).status_code == 403
  response = client.get("/v1/environments/vc/admin-kubeconfig", headers=as_("admin"))
  assert response.status_code == 200
  assert response.json()["kubeconfigData"] == ADMIN_KUBECONFIG


def test_unshare_revokes_everyone_but_the_owner(client, as_, state, credentials):
  environment(client, as_, state, sharedWith=["team-alpha"])
  issue(client, as_, "owner")
  issue(client, as_, "teammate")
  client.delete("/v1/environments/vc/shares/team-alpha", headers=as_("owner"))
  assert credentials.identities["vc"] == {"owner-1"}
  assert issue(client, as_, "teammate").status_code == 403


def test_unshare_succeeds_when_the_vcluster_is_down(client, as_, state, credentials):
  environment(client, as_, state, sharedWith=["team-alpha"])
  credentials.down = True
  assert client.delete("/v1/environments/vc/shares/team-alpha", headers=as_("owner")).status_code == 200


class FakeVcluster:
  """The slice of the Kubernetes API that VclusterCredentials uses, over httpx.MockTransport."""

  def __init__(self):
    self.objects = {}  # path -> body
    self.requests = []

  def handler(self, request: httpx.Request) -> httpx.Response:
    path = request.url.path
    self.requests.append((request.method, str(request.url.host), path))
    if request.method == "POST" and path.endswith("/token"):
      seconds = json.loads(request.content)["spec"]["expirationSeconds"]
      return httpx.Response(201, json={"status": {"token": f"sa-token-{seconds}", "expirationTimestamp": "2026-10-11T12:10:00Z"}})
    if request.method == "POST":
      body = json.loads(request.content)
      key = f"{path}/{body['metadata']['name']}"
      if key in self.objects:
        return httpx.Response(409)
      self.objects[key] = body
      return httpx.Response(201, json=body)
    if request.method == "GET":
      if path not in {key.rsplit("/", 1)[0] for key in self.objects}:
        return httpx.Response(404)
      return httpx.Response(200, json={"items": [body for key, body in self.objects.items() if key.rsplit("/", 1)[0] == path]})
    if request.method == "DELETE":
      return httpx.Response(200) if self.objects.pop(path, None) else httpx.Response(404)
    return httpx.Response(405)


def ready_environment():
  return {"metadata": {"name": "vc"}, "status": {"port": 7100, "kubeconfigData": ADMIN_KUBECONFIG}}


def test_vcluster_issue_creates_identity_once():
  vcluster = FakeVcluster()
  credentials = VclusterCredentials(transport=httpx.MockTransport(vcluster.handler))
  first = credentials.issue(ready_environment(), "owner-1", "owner@example.com")
  credentials.issue(ready_environment(), "owner-1", "owner@example.com")
  assert first == {"token": f"sa-token-{TOKEN_SECONDS}", "expirationTimestamp": "2026-10-11T12:10:00Z"}
  account = vcluster.objects[f"/api/v1/namespaces/{NAMESPACE}/serviceaccounts/owner-1"]
  assert account["metadata"]["annotations"]["platform.wasp.silvios.me/email"] == "owner@example.com"
  binding = vcluster.objects["/apis/rbac.authorization.k8s.io/v1/clusterrolebindings/platform-identity-owner-1"]
  assert binding["subjects"] == [{"kind": "ServiceAccount", "name": "owner-1", "namespace": NAMESPACE}]
  assert binding["roleRef"]["name"] == "cluster-admin"
  # In-cluster address of the vcluster Service, never the host port mapping.
  assert {host for _, host, _ in vcluster.requests} == {"vcluster.env-vc"}


def test_vcluster_revoke_keeps_and_selects():
  vcluster = FakeVcluster()
  credentials = VclusterCredentials(transport=httpx.MockTransport(vcluster.handler))
  for sub in ("owner-1", "mate-1", "mate-2"):
    credentials.issue(ready_environment(), sub, None)
  assert credentials.revoke(ready_environment(), only={"mate-1"}) == ["mate-1"]
  assert credentials.revoke(ready_environment(), keep={"owner-1"}) == ["mate-2"]
  accounts = [key for key in vcluster.objects if "/serviceaccounts/" in key]
  assert accounts == [f"/api/v1/namespaces/{NAMESPACE}/serviceaccounts/owner-1"]
  assert not any(key.endswith("platform-identity-mate-1") for key in vcluster.objects)


def test_vcluster_revoke_before_any_identity():
  credentials = VclusterCredentials(transport=httpx.MockTransport(FakeVcluster().handler))
  assert credentials.revoke(ready_environment()) == []


def test_identity_name_is_a_valid_object_name():
  assert identity_name("6f1c9a8e-2b1d-4c3e-9f00-123456789abc") == "6f1c9a8e-2b1d-4c3e-9f00-123456789abc"
  assert identity_name("Google|User").startswith("sub-")
