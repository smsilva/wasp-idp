"""build create|list|get and the version index (#206): synchronous checks before the Build, then reads."""
import json

import pytest
from fastapi.testclient import TestClient

from fakes import CATALOG_TEAMS, FakeState, FakeTeams
from platform_api.app import create_app
from platform_api.journal import Journal
from tokens import TokenFactory


def connection(name, org, ready):
  condition = {"type": "Ready", "status": "True", "reason": "Verified"} if ready else {"type": "Ready", "status": "False", "reason": "AppNotCreated"}
  return {"metadata": {"name": name}, "spec": {"vendor": "github", "github": {"org": org}}, "status": {"conditions": [condition]}}


def version(component, number, created, commit="a" * 40):
  return {"metadata": {"name": f"{component}.{number}"}, "spec": {
    "component": component, "version": number, "image": f"ghcr.io/wasp-foundry/{component}", "digest": "sha256:" + "b" * 64,
    "commit": commit, "branch": "feat/greetings", "createdAt": created, "build": f"{component}-abc123",
  }}


@pytest.fixture
def state():
  state = FakeState()
  state.create("components", {"metadata": {"name": "greeting-api"}, "spec": {"owner": "team-alpha", "system": "greeter", "source": {"repo": "wasp-foundry/greeting-api"}}})
  state.create("components", {"metadata": {"name": "elsewhere"}, "spec": {"owner": "team-alpha", "system": "greeter", "source": {"repo": "other-org/elsewhere"}}})
  state.create("components", {"metadata": {"name": "no-repo"}, "spec": {"owner": "team-alpha", "system": "greeter"}})
  state.create("scmconnections", connection("wasp-foundry", "wasp-foundry", ready=True))
  state.create("scmconnections", connection("other", "other-org", ready=False))
  return state


@pytest.fixture
def journal_path(tmp_path):
  return tmp_path / "journal.jsonl"


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def client(state, journal_path, tokens):
  return TestClient(create_app(state, Journal(journal_path), tokens.verifier(), teams=FakeTeams(*CATALOG_TEAMS)))


@pytest.fixture
def user(tokens):
  # A user of no team: building needs only a sign-in.
  return {"Authorization": f"Bearer {tokens.issue(sub='user-1', groups=['platform-users'], group_paths=['/platform-users'])}"}


def test_create_writes_the_build(client, state, user, journal_path):
  response = client.post("/v1/builds", json={"component": "greeting-api", "branch": "feat/greetings"}, headers=user)
  assert response.status_code == 202, response.text
  view = response.json()
  assert view["status"] == "pending"
  assert view["name"].startswith("greeting-api-")
  obj = state.get("builds", view["name"])
  assert obj["spec"]["repo"] == "wasp-foundry/greeting-api"
  assert obj["spec"]["scmConnection"] == "wasp-foundry"
  assert obj["spec"]["branch"] == "feat/greetings"
  assert "version" not in obj["spec"]
  assert len(obj["spec"]["requestId"]) == 36
  assert obj["metadata"]["annotations"]["platform.wasp.silvios.me/created-by"] == "user-1"
  entries = [json.loads(line) for line in journal_path.read_text().splitlines()]
  assert entries[0]["kind"] == "Build" and entries[0]["name"] == view["name"] and entries[0]["spec"]["branch"] == "feat/greetings"
  assert entries[1] == {"id": entries[0]["id"], "at": entries[1]["at"], "applied": True}


def test_create_passes_the_version(client, state, user):
  response = client.post("/v1/builds", json={"component": "greeting-api", "branch": "main", "version": "1.0.0-rc.1"}, headers=user)
  assert response.status_code == 202, response.text
  assert state.get("builds", response.json()["name"])["spec"]["version"] == "1.0.0-rc.1"


@pytest.mark.parametrize("body,status,message", [
  ({"component": "nope", "branch": "main"}, 422, "component not found"),
  ({"component": "no-repo", "branch": "main"}, 422, "has no repo"),
  ({"component": "elsewhere", "branch": "main"}, 409, "is not ready"),
  ({"component": "greeting-api", "branch": "main", "version": "v1.0"}, 422, "major"),
  ({"component": "greeting-api", "branch": "feat/../x"}, 422, "branch"),
  ({"component": "greeting-api", "branch": "-x"}, 422, "branch"),
])
def test_refusals_create_nothing(client, state, user, body, status, message):
  response = client.post("/v1/builds", json=body, headers=user)
  assert response.status_code == status, response.text
  assert message in response.text
  assert state.list("builds") == []


def test_no_connection_for_the_org(client, state, user):
  state.delete("scmconnections", "other")
  response = client.post("/v1/builds", json={"component": "elsewhere", "branch": "main"}, headers=user)
  assert response.status_code == 409
  assert "no scm connection for the org 'other-org'" in response.text


def test_requires_sign_in(client):
  assert client.post("/v1/builds", json={"component": "greeting-api", "branch": "main"}).status_code == 401


def test_list_and_get_builds(client, state, user):
  name = client.post("/v1/builds", json={"component": "greeting-api", "branch": "feat/greetings"}, headers=user).json()["name"]
  obj = state.stores["builds"][name]
  obj["status"] = {
    "runUrl": "https://github.com/wasp-foundry/greeting-api/actions/runs/1",
    "run": {"id": 1, "headSha": "a" * 40},
    "conditions": [{"type": "Ready", "status": "False", "reason": "InvalidSpec"}],
    "errors": [{"field": "resources.db.type", "reason": "unknown"}],
  }
  items = client.get("/v1/builds", params={"component": "greeting-api"}, headers=user).json()["items"]
  assert [item["name"] for item in items] == [name]
  assert client.get("/v1/builds", params={"component": "elsewhere"}, headers=user).json()["items"] == []
  view = client.get(f"/v1/builds/{name}", headers=user).json()
  assert view["status"] == "InvalidSpec"
  assert view["commit"] == "a" * 40
  assert view["errors"] == [{"field": "resources.db.type", "reason": "unknown"}]
  assert client.get("/v1/builds/nope", headers=user).status_code == 404


def test_versions_newest_first(client, state, user):
  state.create("versions", version("greeting-api", "0.2.0", "2026-10-10T10:00:00Z"))
  state.create("versions", version("greeting-api", "0.3.0-greetings.1a2b3c4", "2026-10-11T10:00:00Z"))
  state.create("versions", version("elsewhere", "0.1.0", "2026-10-11T11:00:00Z"))
  items = client.get("/v1/versions", params={"component": "greeting-api"}, headers=user).json()["items"]
  assert [item["version"] for item in items] == ["0.3.0-greetings.1a2b3c4", "0.2.0"]
  assert items[0]["image"] == "ghcr.io/wasp-foundry/greeting-api"


def test_a_version_already_in_the_index_is_refused_before_the_dispatch(client, state, user):
  state.create("versions", version("greeting-api", "1.0.0-rc.1", "2026-10-11T10:00:00Z"))
  response = client.post("/v1/builds", json={"component": "greeting-api", "branch": "main", "version": "1.0.0-RC.1"}, headers=user)
  assert response.status_code == 409
  assert "version 1.0.0-rc.1 is already in the index (commit aaaaaaa)" in response.text
  assert state.list("builds") == []
