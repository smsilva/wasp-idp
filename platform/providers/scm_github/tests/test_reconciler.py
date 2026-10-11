"""The five outcomes of a GitHub ScmConnection, with GitHub simulated by httpx.MockTransport."""
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from scm_github_provider.github import GitHubApp
from scm_github_provider.reconciler import REQUIRED, REVALIDATE, VERIFY_ANNOTATION, Reconciler

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
# A throwaway key generated per run: the repo is public, no real App, installation or key here.
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()


class FakeGitHub:
  def __init__(self, app_id=42, installations=None, token_status=201):
    self.app_id = app_id
    self.installations = installations if installations is not None else [installation()]
    self.token_status = token_status
    self.calls = []

  def handler(self, request: httpx.Request) -> httpx.Response:
    self.calls.append(f"{request.method} {request.url.path}")
    token = request.headers["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(token, KEY.public_key(), algorithms=["RS256"])
    if claims["iss"] != str(self.app_id) or claims["exp"] - claims["iat"] > 600:
      return httpx.Response(401, json={"message": "A JSON web token could not be decoded"})
    if request.url.path == "/app":
      return httpx.Response(200, json={"id": self.app_id, "slug": "acme-platform"})
    if request.url.path == "/app/installations":
      return httpx.Response(200, json=self.installations)
    if request.url.path.endswith("/access_tokens"):
      return httpx.Response(self.token_status, json={"token": "ghs_fake", "message": "nope"})
    return httpx.Response(404, json={"message": "Not Found"})

  def factory(self, app_id, key):
    return GitHubApp(app_id, key, transport=httpx.MockTransport(self.handler), base_url="https://api.github.test")


def installation(login="acme", id_=7, selection="all", permissions=None):
  return {"id": id_, "account": {"login": login}, "repository_selection": selection, "permissions": permissions or dict(REQUIRED)}


class FakeStore:
  def __init__(self):
    self.statuses, self.specs = [], []

  def patch_status(self, name, status):
    self.statuses.append(status)

  def patch_spec(self, name, spec):
    self.specs.append(spec)


class FakeSecrets:
  def __init__(self, key=PEM):
    self.key = key

  def private_key(self, name):
    return self.key


def connection(installation_id=None, slug="acme-platform", status=None, requested="2026-10-11T11:59:00Z"):
  github = {"org": "acme", "appId": 42}
  if slug:
    github["appSlug"] = slug
  if installation_id:
    github["installationId"] = installation_id
  annotations = {VERIFY_ANNOTATION: requested} if requested else {}
  return {
    "metadata": {"name": "acme", "annotations": annotations},
    "spec": {"vendor": "github", "github": github, "credentialRef": "scm-acme"},
    "status": status or {},
  }


class Clock:
  def __init__(self):
    self.now = 0.0

  def __call__(self):
    return self.now


def run(github, obj, secrets=None, store=None, clock=None, now=NOW):
  store = store or FakeStore()
  reconciler = Reconciler(store, secrets or FakeSecrets(), github.factory, now=lambda: now, clock=clock or Clock())
  reconciler.reconcile(obj)
  return store, reconciler


def ready(store):
  return store.statuses[-1]["conditions"][0]


def test_verified_records_the_installation():
  github = FakeGitHub()
  store, _ = run(github, connection())
  condition = ready(store)
  assert (condition["status"], condition["reason"]) == ("True", "Verified")
  status = store.statuses[-1]
  assert status["permissions"] == REQUIRED
  assert status["repositorySelection"] == "all"
  assert status["lastValidated"] == "2026-10-11T12:00:00Z"
  assert status["observedVerifyRequest"] == "2026-10-11T11:59:00Z"
  assert store.specs == [{"github": {"installationId": 7}}]
  assert "POST /app/installations/7/access_tokens" in github.calls


def test_records_the_slug_of_an_app_given_by_id():
  store, _ = run(FakeGitHub(), connection(slug=None))
  assert {"github": {"appSlug": "acme-platform"}} in store.specs


def test_not_installed_on_the_org():
  store, _ = run(FakeGitHub(installations=[installation(login="someone-else")]), connection())
  condition = ready(store)
  assert condition["reason"] == "NotInstalled"
  assert "https://github.com/apps/acme-platform/installations/new" in condition["message"]


def test_a_different_installation_is_not_accepted():
  store, _ = run(FakeGitHub(), connection(installation_id=666))
  condition = ready(store)
  assert condition["reason"] == "NotInstalled"
  assert "666" in condition["message"]
  assert store.specs == []


def test_selected_repositories_only():
  store, _ = run(FakeGitHub(installations=[installation(selection="selected")]), connection())
  assert ready(store)["reason"] == "NotAllRepositories"
  assert store.statuses[-1]["repositorySelection"] == "selected"


def test_missing_permissions_are_listed():
  permissions = {**REQUIRED, "administration": "read"}
  del permissions["actions"]
  store, _ = run(FakeGitHub(installations=[installation(permissions=permissions)]), connection())
  condition = ready(store)
  assert condition["reason"] == "MissingPermissions"
  assert "actions:write" in condition["message"]
  assert "administration:write" in condition["message"]


def test_token_refused_is_a_failure():
  store, _ = run(FakeGitHub(token_status=403), connection())
  condition = ready(store)
  assert (condition["status"], condition["reason"]) == ("False", "VerificationFailed")


def test_wrong_key_is_invalid_credentials():
  store, _ = run(FakeGitHub(app_id=99), connection())
  assert ready(store)["reason"] == "InvalidCredentials"


def test_missing_secret():
  store, _ = run(FakeGitHub(), connection(), secrets=FakeSecrets(key=None))
  assert ready(store)["reason"] == "CredentialMissing"


def test_waits_for_the_manifest_flow():
  obj = connection()
  del obj["spec"]["credentialRef"]
  store, _ = run(FakeGitHub(), obj)
  assert store.statuses == []


def verified(last=NOW, requested="2026-10-11T11:59:00Z"):
  return {
    "observedVerifyRequest": requested, "lastValidated": last.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "conditions": [{"type": "Ready", "status": "True", "reason": "Verified"}],
  }


def test_ready_is_revalidated_every_six_hours():
  github = FakeGitHub()
  store, _ = run(github, connection(installation_id=7, status=verified()), now=NOW + timedelta(hours=1))
  assert store.statuses == []
  store, _ = run(github, connection(installation_id=7, status=verified()), now=NOW + REVALIDATE)
  assert ready(store)["reason"] == "Verified"


def test_a_new_verify_request_revalidates_now():
  store, _ = run(FakeGitHub(), connection(installation_id=7, status=verified(), requested="2026-10-11T12:30:00Z"))
  assert store.statuses[-1]["observedVerifyRequest"] == "2026-10-11T12:30:00Z"


def test_not_ready_backs_off():
  github = FakeGitHub(installations=[])
  clock, store = Clock(), FakeStore()
  reconciler = Reconciler(store, FakeSecrets(), github.factory, now=lambda: NOW, clock=clock)
  obj = connection(requested=None)
  reconciler.reconcile(obj)
  assert len(store.statuses) == 1
  reconciler.reconcile(obj)
  assert len(store.statuses) == 1
  clock.now += 31
  reconciler.reconcile(obj)
  assert len(store.statuses) == 2
  clock.now += 31
  reconciler.reconcile(obj)
  assert len(store.statuses) == 2  # the second wait is 60 s


def test_jwt_lives_ten_minutes():
  from scm_github_provider.github import app_jwt

  claims = jwt.decode(app_jwt(42, PEM, now=lambda: 1_000_000), KEY.public_key(), algorithms=["RS256"], options={"verify_exp": False})
  assert claims == {"iat": 999_940, "exp": 1_000_540, "iss": "42"}


def test_permissions_match_the_api_manifest():
  import ast
  from pathlib import Path

  source = (Path(__file__).parents[3] / "api" / "src" / "platform_api" / "scm.py").read_text()
  node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PERMISSIONS")
  assert ast.literal_eval(node.value) == REQUIRED
