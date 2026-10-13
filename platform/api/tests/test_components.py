"""component create (#204): synchronous checks before the CR, the index, the creation progress."""
import json

import pytest
from fastapi.testclient import TestClient

from fakes import CATALOG_TEAMS, FakeState, FakeTeams
from platform_api.app import create_app
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
