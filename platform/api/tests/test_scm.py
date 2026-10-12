"""SCM connections (ADR 0025, #199): admin-only routes, the manifest flow, write-only secrets."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from fakes import FakeSecrets, FakeState
from platform_api.app import create_app
from platform_api.journal import Journal
from platform_api.scm import PERMISSIONS, PLURAL, VERIFY_ANNOTATION, States
from tokens import TokenFactory

ROUTE = "/v1/scm/connections"
# Throwaway values: the repo is public, nothing here is a real App, installation or key.
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEfake\n-----END RSA PRIVATE KEY-----\n"


class Clock:
  def __init__(self):
    self.now = 1000.0

  def __call__(self):
    return self.now


class FakeGitHub:
  """POST /app-manifests/{code}/conversions, over httpx.MockTransport."""

  def __init__(self):
    self.codes = {"good-code": {"id": 42, "slug": "acme-platform", "pem": PEM}}
    self.requests = []

  def handler(self, request: httpx.Request) -> httpx.Response:
    self.requests.append(request)
    code = request.url.path.split("/")[2]
    if request.method == "POST" and code in self.codes:
      return httpx.Response(201, json=self.codes.pop(code))
    return httpx.Response(404, json={"message": "Not Found"})


@pytest.fixture
def state():
  return FakeState()


@pytest.fixture
def secrets():
  return FakeSecrets()


@pytest.fixture
def github():
  return FakeGitHub()


@pytest.fixture
def clock():
  return Clock()


@pytest.fixture
def journal_path(tmp_path):
  return tmp_path / "journal.jsonl"


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def client(state, journal_path, tokens, secrets, github, clock):
  http = httpx.Client(base_url="https://api.github.test", transport=httpx.MockTransport(lambda request: github.handler(request)))
  app = create_app(state, Journal(journal_path), tokens.verifier(), secrets=secrets, github=http, scm_states=States(clock=clock))
  return TestClient(app)


@pytest.fixture
def admin(tokens):
  return {"Authorization": f"Bearer {tokens.issue(sub='admin-1', groups=['platform-admins'])}"}


@pytest.fixture
def user(tokens):
  return {"Authorization": f"Bearer {tokens.issue()}"}


def add(client, admin, name="acme", **extra):
  return client.post(ROUTE, json={"name": name, "vendor": "github", "org": "acme", **extra}, headers=admin)


def state_of(response) -> str:
  return response.json()["next"].split("state=")[1]


def journal(journal_path) -> str:
  return journal_path.read_text()


def test_create_starts_the_manifest_flow(client, admin, state):
  response = add(client, admin, default=True)
  assert response.status_code == 202
  body = response.json()
  assert body["status"] == "AppNotCreated"
  assert body["default"] is True
  assert body["next"].startswith("http://127.0.0.1:9090/v1/scm/connections/acme/github/start?state=")
  assert state.get(PLURAL, "acme")["spec"] == {"vendor": "github", "github": {"org": "acme"}, "default": True}


def test_start_posts_the_manifest_to_the_org(client, admin):
  value = state_of(add(client, admin))
  page = client.get(f"{ROUTE}/acme/github/start", params={"state": value})
  assert page.status_code == 200
  assert f'action="https://github.com/organizations/acme/settings/apps/new?state={value}"' in page.text
  manifest = json.loads(page.text.split('name="manifest" value="')[1].split('"')[0].replace("&quot;", '"'))
  assert manifest["name"] == "acme-platform"
  assert manifest["public"] is False
  assert manifest["hook_attributes"]["active"] is False
  assert manifest["redirect_url"] == "http://127.0.0.1:9090/v1/scm/connections/acme/github/callback"
  assert manifest["setup_url"] == "http://127.0.0.1:9090/v1/scm/connections/acme/github/installed"
  assert manifest["setup_on_update"] is True
  assert manifest["default_permissions"] == PERMISSIONS
  assert PERMISSIONS["actions"] == "write"  # build (#206)


def test_callback_stores_the_key_and_waits_for_the_install(client, admin, state, secrets, journal_path):
  value = state_of(add(client, admin))
  page = client.get(f"{ROUTE}/acme/github/callback", params={"code": "good-code", "state": value})
  assert page.status_code == 200
  assert "https://github.com/apps/acme-platform/installations/new" in page.text
  assert secrets.items["scm-acme"] == {"data": {"privateKey": PEM}, "owner": "ScmConnection/acme"}
  spec = state.get(PLURAL, "acme")["spec"]
  assert spec["github"] == {"org": "acme", "appId": 42, "appSlug": "acme-platform"}
  assert spec["credentialRef"] == "scm-acme"
  body = client.get(f"{ROUTE}/acme", headers=admin).json()
  assert body["status"] == "NotInstalled"
  assert body["installUrl"] == "https://github.com/apps/acme-platform/installations/new"
  # The key is in the SecretStore only: never in a response, the CR or the journal.
  assert "BEGIN" not in json.dumps(body)
  assert "BEGIN" not in json.dumps(state.get(PLURAL, "acme"))
  assert "BEGIN" not in journal(journal_path)
  assert "<redacted, sha256:" in journal(journal_path)


@pytest.mark.parametrize("bad", ["", "forged", "reuse", "expired", "other-connection"])
def test_browser_routes_refuse_bad_states(client, admin, clock, bad):
  value = state_of(add(client, admin))
  add(client, admin, name="other")
  if bad == "reuse":
    assert client.get(f"{ROUTE}/acme/github/callback", params={"code": "good-code", "state": value}).status_code == 200
  elif bad == "expired":
    clock.now += 601
  elif bad == "forged":
    value = "x" * 43
  elif bad == "":
    value = ""
  name = "other" if bad == "other-connection" else "acme"
  assert client.get(f"{ROUTE}/{name}/github/start", params={"state": value}).status_code == 400
  response = client.get(f"{ROUTE}/{name}/github/callback", params={"code": "good-code", "state": value})
  assert response.status_code == 400
  assert "invalid, expired or was already used" in response.text


def test_callback_with_a_spent_code_fails(client, admin, github):
  value = state_of(add(client, admin))
  response = client.get(f"{ROUTE}/acme/github/callback", params={"code": "spent", "state": value})
  assert response.status_code == 400
  assert "404" in response.text


def test_callback_after_the_connection_was_removed_keeps_no_key(client, admin, state, secrets, github):
  value = state_of(add(client, admin))
  handler = github.handler

  def remove_then_answer(request):
    state.stores[PLURAL].pop("acme", None)
    return handler(request)

  github.handler = remove_then_answer
  response = client.get(f"{ROUTE}/acme/github/callback", params={"code": "good-code", "state": value})
  assert response.status_code == 400
  assert "Delete the App on GitHub" in response.text
  assert secrets.items == {}


def test_add_again_restarts_an_unfinished_flow(client, admin):
  first = state_of(add(client, admin))
  second = add(client, admin)
  assert second.status_code == 202
  assert state_of(second) != first
  assert add(client, admin, name="acme", org="other-org").status_code == 409


def test_installed_records_the_installation_and_asks_for_verification(client, admin, state):
  client.get(f"{ROUTE}/acme/github/callback", params={"code": "good-code", "state": state_of(add(client, admin))})
  page = client.get(f"{ROUTE}/acme/github/installed", params={"installation_id": "7", "setup_action": "install"})
  assert page.status_code == 200
  obj = state.get(PLURAL, "acme")
  assert obj["spec"]["github"]["installationId"] == 7
  assert VERIFY_ANNOTATION in obj["metadata"]["annotations"]


@pytest.mark.parametrize("installation_id", ["", "abc", "-1", "1" * 21])
def test_installed_rejects_garbage(client, admin, state, installation_id):
  client.get(f"{ROUTE}/acme/github/callback", params={"code": "good-code", "state": state_of(add(client, admin))})
  assert client.get(f"{ROUTE}/acme/github/installed", params={"installation_id": installation_id}).status_code == 400
  assert "installationId" not in state.get(PLURAL, "acme")["spec"]["github"]


def test_installed_never_overwrites_a_recorded_installation(client, admin, state):
  client.get(f"{ROUTE}/acme/github/callback", params={"code": "good-code", "state": state_of(add(client, admin))})
  client.get(f"{ROUTE}/acme/github/installed", params={"installation_id": "7"})
  client.get(f"{ROUTE}/acme/github/installed", params={"installation_id": "666"})
  assert state.get(PLURAL, "acme")["spec"]["github"]["installationId"] == 7


def test_installed_does_not_touch_a_ready_connection(client, admin, state):
  add(client, admin, appId=42, privateKeyPem=PEM)
  obj = state.get(PLURAL, "acme")
  obj["spec"]["github"]["installationId"] = 7
  obj["status"] = {"conditions": [{"type": "Ready", "status": "True", "reason": "Verified"}]}
  state.stores[PLURAL]["acme"] = obj
  client.get(f"{ROUTE}/acme/github/installed", params={"installation_id": "666"})
  assert state.get(PLURAL, "acme")["spec"]["github"]["installationId"] == 7


def test_create_with_an_existing_app(client, admin, state, secrets, journal_path):
  response = add(client, admin, appId=42, privateKeyPem=PEM)
  assert response.status_code == 202
  body = response.json()
  assert "next" not in body
  assert body["status"] == "Verifying"
  obj = state.get(PLURAL, "acme")
  assert obj["spec"]["github"] == {"org": "acme", "appId": 42}
  assert obj["spec"]["credentialRef"] == "scm-acme"
  assert VERIFY_ANNOTATION in obj["metadata"]["annotations"]
  assert secrets.items["scm-acme"]["data"] == {"privateKey": PEM}
  assert "BEGIN" not in journal(journal_path)


@pytest.mark.parametrize("extra", [{"appId": 42}, {"privateKeyPem": PEM}, {"appId": 42, "privateKeyPem": "not a key"}, {"appId": 0, "privateKeyPem": PEM}])
def test_create_with_half_an_app_is_rejected(client, admin, extra):
  assert add(client, admin, **extra).status_code == 422


@pytest.mark.parametrize("payload", [
  {"name": "Bad", "vendor": "github", "org": "acme"},
  {"name": "acme", "vendor": "gitlab", "org": "acme"},
  {"name": "acme", "vendor": "github", "org": "-acme"},
  {"name": "acme", "vendor": "github", "org": "acme\n"},
  {"name": "acme\n", "vendor": "github", "org": "acme"},
])
def test_create_validates_input(client, admin, payload):
  assert client.post(ROUTE, json=payload, headers=admin).status_code == 422


def test_one_default_at_a_time(client, admin):
  add(client, admin, name="one", default=True)
  add(client, admin, name="two")
  assert client.post(f"{ROUTE}/two/default", headers=admin).json()["default"] is True
  items = {item["name"]: item["default"] for item in client.get(ROUTE, headers=admin).json()["items"]}
  assert items == {"one": False, "two": True}
  add(client, admin, name="three", default=True)
  items = {item["name"]: item["default"] for item in client.get(ROUTE, headers=admin).json()["items"]}
  assert items == {"one": False, "two": False, "three": True}


def test_verify_writes_the_annotation(client, admin, state, journal_path):
  add(client, admin)
  assert client.post(f"{ROUTE}/acme/verify", headers=admin).status_code == 202
  assert VERIFY_ANNOTATION in state.get(PLURAL, "acme")["metadata"]["annotations"]
  assert '"action":"verify"' in journal(journal_path)


def test_verifying_until_the_controller_answers(client, admin, state):
  assert add(client, admin, appId=42, privateKeyPem=PEM).json()["verifying"] is True
  obj = state.get(PLURAL, "acme")
  obj["status"]["observedVerifyRequest"] = obj["metadata"]["annotations"][VERIFY_ANNOTATION]
  state.stores[PLURAL]["acme"] = obj
  assert client.get(f"{ROUTE}/acme", headers=admin).json()["verifying"] is False


def test_delete_removes_the_connection_and_the_secret(client, admin, state, secrets):
  client.get(f"{ROUTE}/acme/github/callback", params={"code": "good-code", "state": state_of(add(client, admin))})
  response = client.delete(f"{ROUTE}/acme", headers=admin)
  assert response.status_code == 200
  assert response.json()["appSettingsUrl"] == "https://github.com/organizations/acme/settings/apps/acme-platform"
  assert state.list(PLURAL) == []
  assert secrets.items == {}
  assert client.get(f"{ROUTE}/acme", headers=admin).status_code == 404


def test_delete_of_an_app_given_by_id_does_not_point_at_deleting_it(client, admin, state):
  add(client, admin, appId=42, privateKeyPem=PEM)
  obj = state.get(PLURAL, "acme")
  obj["spec"]["github"]["appSlug"] = "someone-elses-app"
  state.stores[PLURAL]["acme"] = obj
  assert "appSettingsUrl" not in client.delete(f"{ROUTE}/acme", headers=admin).json()


@pytest.mark.parametrize("method,path", [
  ("POST", ROUTE), ("GET", ROUTE), ("GET", f"{ROUTE}/acme"), ("POST", f"{ROUTE}/acme/verify"),
  ("POST", f"{ROUTE}/acme/default"), ("DELETE", f"{ROUTE}/acme"),
])
def test_non_admins_get_403(client, admin, user, method, path):
  add(client, admin)
  body = {"name": "x", "vendor": "github", "org": "acme"} if method == "POST" and path == ROUTE else None
  assert client.request(method, path, json=body, headers=user).status_code == 403
  assert client.request(method, path, json=body).status_code == 401


