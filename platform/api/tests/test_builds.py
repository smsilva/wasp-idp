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


def registry(name, namespace, default=False):
  return {"metadata": {"name": name}, "spec": {"vendor": "ghcr", "host": "ghcr.io", "namespace": namespace, "default": default, "pull": {"mode": "anonymous"}}}


@pytest.fixture
def state():
  state = FakeState()
  state.create("components", {"metadata": {"name": "greeting-api"}, "spec": {"owner": "team-alpha", "system": "greeter", "source": {"repo": "wasp-foundry/greeting-api"}}})
  state.create("components", {"metadata": {"name": "elsewhere"}, "spec": {"owner": "team-alpha", "system": "greeter", "source": {"repo": "other-org/elsewhere"}}})
  state.create("components", {"metadata": {"name": "no-repo"}, "spec": {"owner": "team-alpha", "system": "greeter"}})
  state.create("scmconnections", connection("wasp-foundry", "wasp-foundry", ready=True))
  state.create("scmconnections", connection("other", "other-org", ready=False))
  state.create("ociregistries", registry("ghcr-wasp-foundry", "wasp-foundry", default=True))
  state.create("ociregistries", registry("ghcr-smsilva", "smsilva"))
  state.create("ociregistries", registry("ghcr-other-org", "other-org"))
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


def bearer(tokens, sub="user-1", groups=("platform-users",), teams=("team-alpha",)):
  paths = [f"/{group}" for group in groups] + [f"/teams/{team}" for team in teams]
  return {"Authorization": f"Bearer {tokens.issue(sub=sub, groups=list(groups), group_paths=paths)}"}


@pytest.fixture
def user(tokens):
  # A member of team-alpha, the owner team of the components below.
  return bearer(tokens)


@pytest.fixture
def outsider(tokens):
  return bearer(tokens, sub="user-2", teams=("team-beta",))


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
  ({"component": "elsewhere", "branch": "main", "registry": "ghcr-other-org"}, 409, "is not ready"),
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
  response = client.post("/v1/builds", json={"component": "elsewhere", "branch": "main", "registry": "ghcr-other-org"}, headers=user)
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


def test_only_the_owner_team_and_admins_build(client, state, tokens, outsider):
  response = client.post("/v1/builds", json={"component": "greeting-api", "branch": "main"}, headers=outsider)
  assert response.status_code == 403
  assert "owner team (team-alpha)" in response.text
  assert state.list("builds") == []
  admin = bearer(tokens, sub="admin-1", groups=("platform-admins",), teams=())
  assert client.post("/v1/builds", json={"component": "greeting-api", "branch": "main"}, headers=admin).status_code == 202


def test_reads_stay_open_to_any_signed_in_user(client, state, user, outsider):
  name = client.post("/v1/builds", json={"component": "greeting-api", "branch": "main"}, headers=user).json()["name"]
  assert client.get(f"/v1/builds/{name}", headers=outsider).status_code == 200
  assert client.get("/v1/versions", params={"component": "greeting-api"}, headers=outsider).status_code == 200


def test_the_build_names_its_registry_and_image(client, state, user):
  name = client.post("/v1/builds", json={"component": "greeting-api", "branch": "main"}, headers=user).json()["name"]
  spec = state.get("builds", name)["spec"]
  assert (spec["registry"], spec["image"]) == ("ghcr-wasp-foundry", "ghcr.io/wasp-foundry/greeting-api")
  view = client.get(f"/v1/builds/{name}", headers=user).json()
  assert (view["registry"], view["image"]) == ("ghcr-wasp-foundry", "ghcr.io/wasp-foundry/greeting-api")


@pytest.mark.parametrize("body,status,message", [
  ({"registry": "nowhere"}, 422, "registry 'nowhere' not found"),
  ({"registry": "ghcr-smsilva"}, 422, "registry ghcr-smsilva (ghcr.io/smsilva) is not writable by the CI of wasp-foundry/greeting-api: GITHUB_TOKEN pushes only to ghcr.io/wasp-foundry (RegistryNotWritableByCI)"),
  ({"registry": "Bad"}, 422, "registry"),
])
def test_registry_refusals(client, state, user, body, status, message):
  response = client.post("/v1/builds", json={"component": "greeting-api", "branch": "main", **body}, headers=user)
  assert response.status_code == status, response.text
  assert message in response.text
  assert state.list("builds") == []


def test_no_default_registry(client, state, user):
  state.delete("ociregistries", "ghcr-wasp-foundry")
  response = client.post("/v1/builds", json={"component": "greeting-api", "branch": "main"}, headers=user)
  assert response.status_code == 409
  assert "no default registry (NoDefaultRegistry)" in response.text
  assert state.list("builds") == []
