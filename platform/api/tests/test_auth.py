import time

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends
from fastapi.testclient import TestClient

from platform_api.app import create_app
from platform_api.auth import require_group
from platform_api.journal import Journal
from test_api import FakeState
from tokens import TokenFactory


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def app(tmp_path, tokens):
  app = create_app(FakeState(), Journal(tmp_path / "journal.jsonl"), tokens.verifier())

  # Test-only route: proves require_group before any real admin route exists.
  @app.get("/v1/admin-only")
  def admin_only(principal=Depends(require_group("platform-admins"))):
    return {"ok": True}

  return app


def call(app, path, token=None):
  headers = {"Authorization": f"Bearer {token}"} if token else {}
  return TestClient(app).get(path, headers=headers)


def test_healthz_needs_no_token(app):
  assert call(app, "/healthz").status_code == 200


def test_missing_token_is_401_with_error_shape(app):
  response = call(app, "/v1/me")
  assert response.status_code == 401
  assert response.json() == {"error": {"code": "unauthorized", "message": "missing bearer token"}}
  assert response.headers["www-authenticate"] == "Bearer"


def test_me_returns_identity_from_token(app, tokens):
  token = tokens.issue(groups=["platform-users", "platform-admins"])
  assert call(app, "/v1/me", token).json() == {
    "sub": "user-1", "email": "dev@example.com", "groups": ["platform-admins", "platform-users"],
  }


@pytest.mark.parametrize("overrides", [
  {"aud": "account"},
  {"iss": "http://keycloak.platform-auth.svc:8080/realms/platform"},
  {"exp": int(time.time()) - 60},
  {"sub": None},
])
def test_rejects_invalid_claims(app, tokens, overrides):
  response = call(app, "/v1/me", tokens.issue(**overrides))
  assert response.status_code == 401
  assert response.json()["error"]["message"] == "invalid token"


def test_rejects_token_signed_by_another_key(app, tokens):
  other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
  assert call(app, "/v1/me", tokens.issue(key=other)).status_code == 401


def test_rejects_non_bearer_scheme(app, tokens):
  response = TestClient(app).get("/v1/me", headers={"Authorization": f"Basic {tokens.issue()}"})
  assert response.status_code == 401


def test_require_group(app, tokens):
  assert call(app, "/v1/admin-only", tokens.issue()).status_code == 403
  assert call(app, "/v1/admin-only", tokens.issue(groups=["platform-admins"])).json() == {"ok": True}


def test_every_v1_route_requires_a_token(app):
  routes = [(route.path, method) for route in app.routes for method in getattr(route, "methods", []) if route.path.startswith("/v1/")]
  assert routes
  for path, method in routes:
    response = TestClient(app).request(method, path.replace("{name}", "x"))
    assert response.status_code == 401, f"{method} {path}"


def test_capabilities(app, tokens):
  items = {item["name"]: item["status"] for item in call(app, "/v1/capabilities", tokens.issue()).json()["items"]}
  assert items["identity"] == "Active"
  assert items["build"] == "NoProviderForCapability"


def test_validation_error_shape(app, tokens):
  response = TestClient(app).post("/v1/environments", json={"name": "Bad", "profile": "ephemeral"}, headers={"Authorization": f"Bearer {tokens.issue()}"})
  assert response.status_code == 422
  assert response.json()["error"]["code"] == "invalid_request"
