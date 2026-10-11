"""workload spec validate|get (#291): the Score gate of the build on a local file, and the spec of a version."""
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from fakes import CATALOG_TEAMS, FakeState, FakeTeams
from platform_api.app import create_app
from platform_api.journal import Journal
from test_builds import bearer, version
from tokens import TokenFactory

SEED = (Path(__file__).parents[2] / "templates" / "python-service" / "content" / "app-spec.yaml").read_text()
# The seed renders ${{ values.* }}; a rendered app-spec.yaml carries the values.
SPEC = SEED.replace("${{ values.name }}", "greeting-api").replace("${{ values.port }}", "8000")


def indexed(component, number, created, branch="feat/greetings", app_spec=True):
  obj = version(component, number, created)
  obj["spec"]["branch"] = branch
  if app_spec:
    obj["spec"]["appSpec"] = {**yaml.safe_load(SPEC), "metadata": {"name": component, "built": number}}
  return obj


@pytest.fixture
def state():
  state = FakeState()
  state.create("components", {"metadata": {"name": "greeting-api"}, "spec": {"owner": "team-alpha", "system": "greeter"}})
  state.create("components", {"metadata": {"name": "unbuilt"}, "spec": {"owner": "team-alpha", "system": "greeter"}})
  state.create("resources", {"metadata": {"name": "shared-db"}, "spec": {"type": "postgres", "system": "greeter", "owner": "team-alpha"}})
  state.create("versions", indexed("greeting-api", "1.0.0", "2026-10-01T10:00:00Z", branch="main"))
  state.create("versions", indexed("greeting-api", "1.1.0-greetings.1", "2026-10-02T10:00:00Z"))
  state.create("versions", indexed("greeting-api", "1.1.0-greetings.2", "2026-10-03T10:00:00Z"))
  state.create("versions", indexed("greeting-api", "0.9.0", "2026-09-01T10:00:00Z", branch="old", app_spec=False))
  return state


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def client(state, tmp_path, tokens):
  return TestClient(create_app(state, Journal(tmp_path / "journal.jsonl"), tokens.verifier(), teams=FakeTeams(*CATALOG_TEAMS)))


@pytest.fixture
def anyone(tokens):
  # Outside the owner team: validating is open to any signed-in user.
  return bearer(tokens, sub="user-2", teams=("team-beta",))


@pytest.fixture
def owner(tokens):
  # A member of team-alpha, the owner team of greeting-api.
  return bearer(tokens)


@pytest.fixture
def admin(tokens):
  return bearer(tokens, sub="admin-1", groups=("platform-users", "platform-admins"), teams=())


def test_validate_a_valid_spec(client, anyone):
  response = client.post("/v1/workload-specs:validate", json={"content": SPEC}, headers=anyone)
  assert response.status_code == 200, response.text
  assert response.json() == {
    "valid": True, "errors": [],
    "resources": [{"name": "db", "type": "postgres"}, {"name": "dns", "type": "dns"}, {"name": "route", "type": "route"}],
  }


def test_validate_runs_the_gate_of_the_build(client, anyone):
  spec = SPEC.replace("type: postgres", "type: redis\n  shared:\n    type: postgres\n    id: shared-db\n  cache:\n    type: postgres\n    id: shared-cache")
  body = client.post("/v1/workload-specs:validate", json={"content": spec}, headers=anyone).json()
  assert body["valid"] is False
  assert {item["field"] for item in body["errors"]} == {"resources.db.type", "resources.cache.id"}


def test_validate_reports_the_schema(client, anyone):
  body = client.post("/v1/workload-specs:validate", json={"content": "apiVersion: platform/v1\n"}, headers=anyone).json()
  assert body["valid"] is False
  assert body["errors"]


def test_validate_bounds_the_content(client, anyone):
  response = client.post("/v1/workload-specs:validate", json={"content": "#" * (64 * 1024 + 1)}, headers=anyone)
  assert response.status_code == 422


def test_validate_needs_a_signed_in_user(client):
  assert client.post("/v1/workload-specs:validate", json={"content": SPEC}).status_code == 401


def test_get_the_newest_version(client, owner):
  response = client.get("/v1/catalog/components/greeting-api/spec", headers=owner)
  assert response.status_code == 200, response.text
  body = response.json()
  assert body["version"] == "1.1.0-greetings.2"
  assert body["commit"] == "a" * 40
  assert body["image"] == "ghcr.io/wasp-foundry/greeting-api"
  assert body["appSpec"]["metadata"] == {"name": "greeting-api", "built": "1.1.0-greetings.2"}


def test_get_a_version(client, owner):
  body = client.get("/v1/catalog/components/greeting-api/spec", params={"version": "1.0.0"}, headers=owner).json()
  assert (body["version"], body["branch"]) == ("1.0.0", "main")


def test_get_the_newest_of_a_branch(client, owner):
  body = client.get("/v1/catalog/components/greeting-api/spec", params={"branch": "main"}, headers=owner).json()
  assert body["version"] == "1.0.0"
  body = client.get("/v1/catalog/components/greeting-api/spec", params={"branch": "feat/greetings"}, headers=owner).json()
  assert body["version"] == "1.1.0-greetings.2"


def test_version_and_branch_are_exclusive(client, owner):
  response = client.get("/v1/catalog/components/greeting-api/spec", params={"version": "1.0.0", "branch": "main"}, headers=owner)
  assert response.status_code == 422


@pytest.mark.parametrize("component, params", [
  ("nobody", {}),
  ("unbuilt", {}),
  ("greeting-api", {"version": "9.9.9"}),
  ("greeting-api", {"branch": "feat/none"}),
])
def test_not_found(client, owner, component, params):
  assert client.get(f"/v1/catalog/components/{component}/spec", params=params, headers=owner).status_code == 404


def test_a_version_indexed_before_the_spec_is_spec_not_indexed(client, owner):
  response = client.get("/v1/catalog/components/greeting-api/spec", params={"version": "0.9.0"}, headers=owner)
  assert response.status_code == 409
  assert "SpecNotIndexed" in response.json()["error"]["message"]


def test_get_is_for_the_owner_team_and_admins(client, anyone, admin):
  response = client.get("/v1/catalog/components/greeting-api/spec", headers=anyone)
  assert response.status_code == 403
  assert "team-alpha" in response.json()["error"]["message"]
  assert client.get("/v1/catalog/components/greeting-api/spec", headers=admin).status_code == 200
