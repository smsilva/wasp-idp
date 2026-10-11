"""Template routes (ADR 0024): CRUD, one default per type, admin-only writes."""
import json

import pytest
from fastapi.testclient import TestClient

from fakes import CATALOG_TEAMS, FakeState, FakeTeams
from platform_api.app import create_app
from platform_api.journal import Journal
from tokens import TokenFactory

ROUTE = "/v1/catalog/templates"
REPO = "https://github.com/smsilva/wasp-idp"


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
  return TestClient(create_app(state, Journal(journal_path), tokens.verifier(), teams=FakeTeams(*CATALOG_TEAMS)))


def bearer(tokens, **claims):
  return {"Authorization": f"Bearer {tokens.issue(**claims)}"}


@pytest.fixture
def admin(tokens):
  return bearer(tokens, sub="admin-1", groups=["platform-admins"])


@pytest.fixture
def user(tokens):
  return bearer(tokens)


def body(name="python-service", type_="service", default=False, **extra):
  return {
    "name": name, "type": type_, "owner": "team-platform", "default": default,
    "source": {"repo": REPO, "path": f"platform/templates/{name}/content", "ref": "v1"},
    **extra,
  }


def create(client, headers, **kwargs):
  response = client.post(ROUTE, json=body(**kwargs), headers=headers)
  assert response.status_code == 201, response.text
  return response.json()


def defaults(state):
  return sorted(name for name, obj in state.stores["templates"].items() if obj["spec"].get("default"))


def test_create_and_get(client, admin, user, state):
  created = create(client, admin, parameters={"type": "object", "properties": {"port": {"type": "integer", "default": 8000}}}, copyWithoutRendering=[".github/workflows/*"])
  assert created["kind"] == "Template"
  assert created["source"] == {"repo": REPO, "path": "platform/templates/python-service/content", "ref": "v1"}
  got = client.get(f"{ROUTE}/python-service", headers=user).json()
  assert (got["type"], got["default"], got["parameters"]["properties"]["port"]["default"]) == ("service", False, 8000)
  assert got["copyWithoutRendering"] == [".github/workflows/*"]
  assert state.stores["templates"]["python-service"]["apiVersion"] == "catalog.platform.wasp.silvios.me/v1alpha1"


def test_list_sorted_for_everyone(client, admin, user):
  create(client, admin, name="b-service")
  create(client, admin, name="a-site", type_="website")
  items = client.get(ROUTE, headers=user).json()["items"]
  assert [item["name"] for item in items] == ["a-site", "b-service"]


@pytest.mark.parametrize("verb", ["create", "default", "delete"])
def test_user_is_403_on_writes(client, admin, user, verb):
  create(client, admin)
  if verb == "create":
    response = client.post(ROUTE, json=body(name="other"), headers=user)
  elif verb == "default":
    response = client.post(f"{ROUTE}/python-service/default", headers=user)
  else:
    response = client.delete(f"{ROUTE}/python-service", headers=user)
  assert response.status_code == 403
  assert "platform-admins" in response.json()["error"]["message"]


def test_create_default_unsets_the_previous_one(client, admin, state, journal_path):
  create(client, admin, name="python-service", default=True)
  create(client, admin, name="go-service", default=True)
  create(client, admin, name="site", type_="website", default=True)
  assert defaults(state) == ["go-service", "site"]
  entries = [json.loads(line) for line in journal_path.read_text().splitlines() if "action" in line]
  assert ("update", "python-service") in {(entry["action"], entry["name"]) for entry in entries}


def test_default_route_moves_the_default(client, admin, state):
  create(client, admin, name="python-service", default=True)
  create(client, admin, name="go-service")
  response = client.post(f"{ROUTE}/go-service/default", headers=admin)
  assert response.status_code == 200, response.text
  assert response.json()["default"] is True
  assert defaults(state) == ["go-service"]


def test_delete_default_with_others_of_the_type_is_409(client, admin, state):
  create(client, admin, name="python-service", default=True)
  create(client, admin, name="go-service")
  response = client.delete(f"{ROUTE}/python-service", headers=admin)
  assert response.status_code == 409
  assert response.json()["error"]["message"] == (
    "template 'python-service' is the default for type 'service': make another one the default first (go-service)"
  )
  assert client.delete(f"{ROUTE}/go-service", headers=admin).status_code == 204
  assert client.delete(f"{ROUTE}/python-service", headers=admin).status_code == 204
  assert state.list("templates") == []


@pytest.mark.parametrize("change,message", [
  ({"type": "cli"}, "type"),
  ({"name": "Python"}, "name"),
  ({"source": {"repo": REPO, "path": "../x", "ref": "v1"}}, "source.path"),
  ({"source": {"repo": REPO, "path": "/abs", "ref": "v1"}}, "source.path"),
  ({"source": {"repo": "file:///etc", "path": "x", "ref": "v1"}}, "source.repo"),
  ({"source": {"repo": REPO, "path": "x", "ref": "a b"}}, "source.ref"),
  ({"parameters": {"type": "object", "properties": {"owner": {"type": "string"}}}}, "parameters"),
  ({"parameters": {"type": "array"}}, "parameters"),
])
def test_invalid_spec_is_422(client, admin, change, message):
  response = client.post(ROUTE, json={**body(), **change}, headers=admin)
  assert response.status_code == 422, response.text
  assert response.json()["error"]["message"].startswith(message)


def test_duplicate_is_409(client, admin):
  create(client, admin)
  assert client.post(ROUTE, json=body(), headers=admin).status_code == 409


def test_unknown_is_404(client, user):
  assert client.get(f"{ROUTE}/nope", headers=user).status_code == 404


def test_create_default_unsets_the_others_before_creating(client, admin, state):
  create(client, admin, name="python-service", default=True)
  # A conflict while unsetting the previous default must not leave a new default behind a 409.
  original = state.replace

  def conflict(plural, body):
    from platform_api.state import Conflict
    raise Conflict(body["metadata"]["name"])

  state.replace = conflict
  response = client.post(ROUTE, json=body(name="go-service", default=True), headers=admin)
  state.replace = original
  assert response.status_code == 409
  assert "go-service" not in state.stores["templates"]


def test_owner_must_be_a_team(client, admin):
  response = client.post(ROUTE, json={**body(), "owner": "nobody"}, headers=admin)
  assert response.status_code == 422
  assert response.json()["error"]["message"] == "template 'python-service': team 'nobody' not found"


def test_team_owning_a_template_is_in_use(client, admin):
  create(client, admin)
  response = client.delete("/v1/teams/team-platform", headers=admin)
  assert response.status_code == 409
  assert "template/python-service" in response.json()["error"]["message"]
