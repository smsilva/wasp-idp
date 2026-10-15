"""component create (#204): synchronous checks before the CR, the index, the creation progress."""
import json

import pytest
from fastapi.testclient import TestClient

from fakes import CATALOG_TEAMS, FakeState, FakeTeams
from platform_api.app import create_app
from platform_api.catalog import CREATED_BY_ANNOTATION
from platform_api.journal import Journal
from platform_api.teams import users_of
from tokens import TokenFactory

ROUTE = "/v1/catalog/components"
SOURCE = {"repo": "https://github.com/smsilva/wasp-idp", "path": "platform/templates/python-service/content", "ref": "abc123"}


@pytest.fixture
def state():
  state = FakeState()
  state.create("systems", {"metadata": {"name": "greeter"}, "spec": {"owner": "team-alpha", "domain": "core"}})
  state.create("templates", {"metadata": {"name": "python-service"}, "spec": {
    "type": "service", "owner": "team-platform", "default": True, "source": SOURCE,
    "parameters": {"type": "object", "properties": {"port": {"type": "integer", "default": 8000}}},
    "copyWithoutRendering": [".github/workflows/*"],
  }})
  state.create("templates", {"metadata": {"name": "static-site"}, "spec": {"type": "website", "owner": "team-platform", "source": SOURCE}})
  state.create("scmconnections", connection("wasp-foundry", ready=True, default=True))
  return state


def connection(name, ready, default=False, visibility=None):
  github = {"org": name}
  if visibility:
    github["defaultVisibility"] = visibility
  spec = {"vendor": "github", "github": github}
  if default:
    spec["default"] = True
  condition = {"type": "Ready", "status": "True", "reason": "Verified"} if ready else {"type": "Ready", "status": "False", "reason": "AppNotCreated"}
  return {"metadata": {"name": name}, "spec": spec, "status": {"conditions": [condition]}}


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
  return bearer(tokens)


def create(client, headers, **body):
  return client.post(ROUTE, json={"name": "greeting-api", "system": "greeter", **body}, headers=headers)


def test_create_writes_the_creation_with_the_resolved_template(client, state, user):
  response = create(client, user, params={"port": "9000"})
  assert response.status_code == 202, response.text
  view = response.json()
  assert view["template"] == {"name": "python-service", "ref": "abc123", "default": True}
  assert view["status"] == "pending"
  obj = state.get("componentcreations", "greeting-api")
  assert obj["spec"]["owner"] == "team-alpha"
  assert obj["spec"]["params"] == {"port": 9000}
  assert obj["spec"]["template"]["source"] == SOURCE
  assert obj["spec"]["template"]["copyWithoutRendering"] == [".github/workflows/*"]
  assert obj["spec"]["scmConnection"] == "wasp-foundry"
  assert obj["spec"]["visibility"] == "public"
  assert obj["metadata"]["annotations"]["platform.wasp.silvios.me/created-by"] == "user-1"


def test_template_and_visibility_from_the_request_or_the_connection(client, state, user):
  state.create("scmconnections", connection("other-org", ready=True, visibility="private"))
  response = create(client, user, template="python-service", scm="other-org")
  assert response.status_code == 202, response.text
  assert response.json()["template"]["default"] is False
  assert state.get("componentcreations", "greeting-api")["spec"]["visibility"] == "private"
  response = create(client, user, name="other-api", scm="other-org", visibility="public")
  assert state.get("componentcreations", "other-api")["spec"]["visibility"] == "public"


def test_unknown_system_is_422(client, state, user):
  response = create(client, user, system="nope")
  assert response.status_code == 422
  assert "system 'nope' not found" in response.json()["error"]["message"]
  assert state.list("componentcreations") == []


@pytest.mark.parametrize("plural", ["components", "componentcreations"])
def test_name_taken_is_409(client, state, user, plural):
  state.create(plural, {"metadata": {"name": "greeting-api"}, "spec": {}})
  response = create(client, user)
  assert response.status_code == 409


def test_param_outside_the_schema_is_422_with_the_field(client, state, user):
  response = create(client, user, params={"colour": "blue"})
  assert response.status_code == 422
  assert "colour: not a parameter of python-service" in response.json()["error"]["message"]
  response = create(client, user, params={"port": "x"})
  assert "port: 'x' is not an integer" in response.json()["error"]["message"]
  assert state.list("componentcreations") == []


def test_template_checks(client, state, user):
  assert create(client, user, template="nope").status_code == 422
  assert create(client, user, type="library").status_code == 422  # no default for library
  response = create(client, user, type="service", template="static-site")
  assert response.status_code == 422
  assert "of type 'website'" in response.json()["error"]["message"]


def test_connection_not_ready_is_409(client, state, user):
  state.create("scmconnections", connection("pending-org", ready=False))
  response = create(client, user, scm="pending-org")
  assert response.status_code == 409
  assert "AppNotCreated" in response.json()["error"]["message"]
  assert create(client, user, scm="missing").status_code == 422
  assert state.list("componentcreations") == []


def test_without_a_default_connection_is_409(client, state, user):
  state.stores["scmconnections"].clear()
  response = create(client, user)
  assert response.status_code == 409
  assert "--scm" in response.json()["error"]["message"]


def test_owner_is_one_known_team(client, state, tokens):
  response = create(client, bearer(tokens, teams=()))
  assert response.status_code == 422
  assert "--owner" in response.json()["error"]["message"]
  # A team joined after the token was issued is not in it yet.
  assert "platform login --refresh" in response.json()["error"]["message"]
  response = create(client, bearer(tokens, teams=("team-alpha", "team-beta")))
  assert response.status_code == 422
  assert "platform login" not in response.json()["error"]["message"]
  assert create(client, bearer(tokens, teams=()), owner="ghosts").status_code == 422
  assert create(client, bearer(tokens, teams=()), owner="team-beta").status_code == 202


def test_name_rejects_a_trailing_newline(client, user):
  assert create(client, user, name="greeting-api\n").status_code == 422


def test_prd_reaches_the_cr_but_only_its_hash_the_journal(client, state, user, journal_path):
  prd = "# Problem\nThe secret plan.\n"
  assert create(client, user, prd=prd).status_code == 202
  assert state.get("componentcreations", "greeting-api")["spec"]["prd"] == prd
  journal = journal_path.read_text()
  assert "secret plan" not in journal
  entry = json.loads(journal.splitlines()[0])
  assert entry["spec"]["prd"].startswith("<redacted, sha256:")


def test_prd_too_long_is_422(client, user):
  assert create(client, user, prd="x" * (64 * 1024 + 1)).status_code == 422


def test_list_and_get_read_the_index(client, state, user):
  for name, system, owner in [("b-api", "greeter", "team-alpha"), ("a-api", "greeter", "team-beta"), ("c-api", "other", "team-alpha")]:
    state.create("components", {"metadata": {"name": name}, "spec": {
      "system": system, "owner": owner, "type": "service", "lifecycle": "experimental",
      "source": {"repo": f"wasp-foundry/{name}", "template": "python-service@abc123", "origin": "created"},
    }})
  items = client.get(ROUTE, headers=user).json()["items"]
  assert [item["name"] for item in items] == ["a-api", "b-api", "c-api"]
  assert [item["name"] for item in client.get(ROUTE, params={"system": "greeter", "owner": "team-alpha"}, headers=user).json()["items"]] == ["b-api"]
  got = client.get(f"{ROUTE}/a-api", headers=user).json()
  assert got["repo"] == "wasp-foundry/a-api"
  assert got["template"] == "python-service@abc123"
  assert client.get(f"{ROUTE}/nope", headers=user).status_code == 404


def test_creation_is_visible_to_who_requested_it_and_admins(client, tokens, user):
  assert create(client, user).status_code == 202
  assert client.get(f"{ROUTE}/greeting-api/creation", headers=user).status_code == 200
  assert client.get(f"{ROUTE}/greeting-api/creation", headers=bearer(tokens, sub="user-2")).status_code == 403
  admin = bearer(tokens, sub="admin-1", groups=("platform-admins",))
  assert client.get(f"{ROUTE}/greeting-api/creation", headers=admin).status_code == 200
  assert client.get(f"{ROUTE}/nope/creation", headers=user).status_code == 404


def test_a_component_keeps_its_team_in_use(state):
  state.create("components", {"metadata": {"name": "greeting-api"}, "spec": {"owner": "team-alpha", "system": "greeter", "source": {"repo": "x/y"}}})
  assert "component/greeting-api" in users_of(state, "team-alpha")


def creation(state, name="greeting-api", sub="user-1", reason=None, ready=False, since="2026-10-10T01:00:00Z", done=()):
  """A ComponentCreation as the provider leaves it: steps in `done` True, then Ready."""
  conditions = [{"type": step, "status": "True", "reason": "Done"} for step in done]
  if ready:
    conditions.append({"type": "Ready", "status": "True", "reason": "Created", "lastTransitionTime": since})
  elif reason:
    conditions.append({"type": "Ready", "status": "False", "reason": reason, "message": f"{reason} message", "lastTransitionTime": since})
  return state.create("componentcreations", {
    "metadata": {"name": name, "annotations": {CREATED_BY_ANNOTATION: sub}},
    "spec": {"system": "greeter", "owner": "team-alpha"},
    "status": {"conditions": conditions},
  })


def admin_of(tokens):
  return bearer(tokens, sub="admin-1", groups=("platform-admins",))


@pytest.mark.parametrize("reason", ["RepoAlreadyExists", "RepoGone", "ComponentExists", "GitHubRejected"])
def test_a_stopped_creation_holds_the_name_and_says_the_way_out(client, state, user, reason):
  creation(state, reason=reason)
  response = create(client, user)
  assert response.status_code == 409
  message = response.json()["error"]["message"]
  assert f"stopped at {reason}" in message
  assert "--replace" in message
  assert "platform catalog component creation delete greeting-api" in message


@pytest.mark.parametrize("kwargs, said", [
  ({}, "still being created"),
  ({"reason": "GitHubUnavailable"}, "still being created"),
  ({"reason": "ConnectionNotReady"}, "still being created"),
  ({"ready": True}, "already created"),
])
def test_replace_does_not_apply_to_a_running_or_ready_creation(client, state, user, kwargs, said):
  old = creation(state, **kwargs)
  for body in ({}, {"replace": True}):
    response = create(client, user, **body)
    assert response.status_code == 409
    assert said in response.json()["error"]["message"]
  assert state.get("componentcreations", "greeting-api")["metadata"]["uid"] == old["metadata"]["uid"]


def test_replace_takes_the_place_of_a_stopped_creation(client, state, user, journal_path):
  old = creation(state, reason="RepoAlreadyExists")
  response = create(client, user, replace=True)
  assert response.status_code == 202, response.text
  new = state.get("componentcreations", "greeting-api")
  assert new["metadata"]["uid"] != old["metadata"]["uid"]
  assert new.get("status") is None
  actions = [entry["action"] for entry in map(json.loads, journal_path.read_text().splitlines()) if "action" in entry]
  assert actions == ["delete", "create"]


def test_replace_is_for_who_requested_it_and_admins(client, state, tokens):
  creation(state, reason="RepoAlreadyExists", sub="user-1")
  other = bearer(tokens, sub="user-2")
  response = create(client, other, replace=True)
  assert response.status_code == 403
  assert state.get("componentcreations", "greeting-api")["status"]["conditions"][-1]["reason"] == "RepoAlreadyExists"
  assert create(client, admin_of(tokens), replace=True).status_code == 202


def test_replace_without_a_creation_just_creates(client, state, user):
  assert create(client, user, replace=True).status_code == 202


def test_replace_does_not_free_a_name_in_the_index(client, state, user):
  state.create("components", {"metadata": {"name": "greeting-api"}, "spec": {}})
  assert create(client, user, replace=True).status_code == 409


CREATIONS_ROUTE = "/v1/catalog/component-creations"


def test_list_creations_shows_each_person_their_own_and_admins_all(client, state, tokens, user):
  creation(state, name="a-api", sub="user-1", reason="RepoAlreadyExists", done=("Validated", "Rendered"))
  creation(state, name="b-api", sub="user-2")
  mine = client.get(CREATIONS_ROUTE, headers=user).json()["items"]
  assert [item["name"] for item in mine] == ["a-api"]
  assert [item["name"] for item in client.get(CREATIONS_ROUTE, headers=admin_of(tokens)).json()["items"]] == ["a-api", "b-api"]
  item = mine[0]
  assert item["status"] == "RepoAlreadyExists"
  assert item["step"] == "RepoCreated"
  assert item["requestedBy"] == "user-1"
  assert item["freesAt"] == "2026-10-11T01:00:00Z"


def test_list_creations_has_no_frees_at_while_running(client, state, user):
  creation(state, reason="GitHubUnavailable")
  item = client.get(CREATIONS_ROUTE, headers=user).json()["items"][0]
  assert item["freesAt"] is None
  assert item["step"] == "Validated"


def test_a_ready_creation_has_no_step_left(client, state, user):
  creation(state, ready=True, done=("Validated", "Rendered", "RepoCreated", "Pushed", "Protected", "Registered"))
  item = client.get(CREATIONS_ROUTE, headers=user).json()["items"][0]
  assert item["step"] is None
  assert item["freesAt"] == "2026-10-11T01:00:00Z"


def test_a_component_named_creations_is_not_shadowed(client, state, user):
  assert client.get(f"{ROUTE}/creations", headers=user).status_code == 404


def test_delete_a_stopped_or_ready_creation_frees_the_name(client, state, user, journal_path):
  creation(state, reason="RepoAlreadyExists")
  creation(state, name="b-api", ready=True)
  assert client.delete(f"{ROUTE}/greeting-api/creation", headers=user).status_code == 204
  assert client.delete(f"{ROUTE}/b-api/creation", headers=user).status_code == 204
  assert state.list("componentcreations") == []
  entries = [entry for entry in map(json.loads, journal_path.read_text().splitlines()) if "action" in entry]
  assert [(entry["action"], entry["kind"], entry["name"]) for entry in entries] == [
    ("delete", "ComponentCreation", "greeting-api"), ("delete", "ComponentCreation", "b-api"),
  ]
  assert create(client, user).status_code == 202


@pytest.mark.parametrize("kwargs", [{}, {"reason": "GitHubUnavailable"}])
def test_delete_a_running_creation_is_409(client, state, user, kwargs):
  creation(state, **kwargs)
  response = client.delete(f"{ROUTE}/greeting-api/creation", headers=user)
  assert response.status_code == 409
  assert "still being created" in response.json()["error"]["message"]
  assert len(state.list("componentcreations")) == 1


def test_delete_a_creation_is_for_who_requested_it_and_admins(client, state, tokens, user):
  creation(state, reason="RepoAlreadyExists")
  assert client.delete(f"{ROUTE}/greeting-api/creation", headers=bearer(tokens, sub="user-2")).status_code == 403
  assert client.delete(f"{ROUTE}/greeting-api/creation", headers=admin_of(tokens)).status_code == 204
  assert client.delete(f"{ROUTE}/greeting-api/creation", headers=user).status_code == 404


def indexed(state, name="greeting-api"):
  return state.create("components", {"metadata": {"name": name}, "spec": {"system": "greeter", "owner": "team-alpha", "source": {"repo": f"wasp-foundry/{name}"}}})


def build(state, name, created, component="greeting-api", ready=True, version="0.1.0"):
  status = {"conditions": [{"type": "Ready", "status": "True" if ready else "False", "reason": "Registered" if ready else "InvalidSpec"}],
            "run": {"headSha": "c" * 40}, "runUrl": f"https://github.com/wasp-foundry/{component}/actions/runs/1"}
  if ready:
    status["result"] = {"version": version, "commit": "d" * 40}
  state.create("builds", {"metadata": {"name": name}, "spec": {"component": component, "branch": "main"}, "status": status})
  state.stores["builds"][name]["metadata"]["creationTimestamp"] = created


def registered(state, number, created, component="greeting-api"):
  return state.create("versions", {"metadata": {"name": f"{component}.{number}"}, "spec": {
    "component": component, "version": number, "commit": "e" * 40, "branch": "main", "createdAt": created, "build": f"{component}-abc123",
  }})


def test_get_shows_what_the_component_generated(client, state, user):
  indexed(state)
  indexed(state, "other-api")
  creation(state, ready=True)
  for day in range(1, 8):
    build(state, f"greeting-api-{day:06d}", f"2026-10-0{day}T00:00:00Z", version=f"0.{day}.0")
    registered(state, f"0.{day}.0", f"2026-10-0{day}T00:00:00Z")
  build(state, "other-api-000001", "2026-10-09T00:00:00Z", component="other-api")
  registered(state, "9.9.9", "2026-10-09T00:00:00Z", component="other-api")
  body = client.get(f"{ROUTE}/greeting-api", headers=user).json()
  assert body["creation"]["status"] == "ready"
  assert [item["name"] for item in body["builds"]] == [f"greeting-api-{day:06d}" for day in (7, 6, 5, 4, 3)]
  assert body["builds"][0] == {
    "name": "greeting-api-000007", "branch": "main", "status": "ready", "version": "0.7.0", "commit": "d" * 40,
    "runUrl": "https://github.com/wasp-foundry/greeting-api/actions/runs/1", "createdAt": "2026-10-07T00:00:00Z",
  }
  assert [item["version"] for item in body["versions"]] == ["0.7.0", "0.6.0", "0.5.0", "0.4.0", "0.3.0"]
  assert body["runningIn"] == []


def test_get_omits_a_creation_the_caller_cannot_see(client, state, tokens, user):
  indexed(state)
  creation(state, reason="ComponentExists")
  assert client.get(f"{ROUTE}/greeting-api", headers=bearer(tokens, sub="user-2")).json()["creation"] is None
  assert client.get(f"{ROUTE}/greeting-api", headers=admin_of(tokens)).json()["creation"]["status"] == "ComponentExists"


def test_get_without_creation_builds_or_versions(client, state, user):
  indexed(state)
  body = client.get(f"{ROUTE}/greeting-api", headers=user).json()
  assert (body["creation"], body["builds"], body["versions"]) == (None, [], [])


def test_get_a_pending_build_has_no_version(client, state, user):
  indexed(state)
  build(state, "greeting-api-000001", "2026-10-01T00:00:00Z", ready=False)
  item = client.get(f"{ROUTE}/greeting-api", headers=user).json()["builds"][0]
  assert (item["status"], item["version"], item["commit"]) == ("InvalidSpec", None, "c" * 40)
