import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from platform_api.app import create_app
from platform_api.journal import Journal
from platform_api.teams import KeycloakTeams
from fakes import FakeState
from tokens import TokenFactory


class FakeKeycloak:
  """The slice of the realm admin API that KeycloakTeams uses, over httpx.MockTransport."""

  def __init__(self, groups=("platform-admins", "platform-users")):
    self.groups = {}
    self.members = {}
    self.users = {}
    self.token_requests = 0
    self.fail_with = None
    for name in groups:
      self._add_group(name, None)

  def _add_group(self, name, parent):
    group_id = str(uuid.uuid4())
    path = f"{self.groups[parent]['path']}/{name}" if parent else f"/{name}"
    self.groups[group_id] = {"id": group_id, "name": name, "path": path, "parent": parent}
    self.members[group_id] = set()
    return group_id

  def add_user(self, username, email, verified=True):
    self.users[str(uuid.uuid4())] = {"username": username, "email": email, "emailVerified": verified}

  def group_by_path(self, path):
    return next((group for group in self.groups.values() if group["path"] == path), None)

  def handler(self, request: httpx.Request) -> httpx.Response:
    if self.fail_with:
      return httpx.Response(self.fail_with)
    path = request.url.path
    if path.endswith("/protocol/openid-connect/token"):
      self.token_requests += 1
      return httpx.Response(200, json={"access_token": "admin-token", "expires_in": 300})
    assert request.headers["authorization"] == "Bearer admin-token"
    parts = path.removeprefix("/admin/realms/platform/").split("/")
    params = request.url.params
    if parts == ["groups"] and request.method == "GET":
      # Like Keycloak: the top-level groups whose subtree has an exact match.
      matches = [g for g in self.groups.values() if g["name"] == params["search"]]
      roots = {self._root(g)["id"]: self._root(g) for g in matches}
      return httpx.Response(200, json=[self._view(g) for g in roots.values()])
    if parts == ["groups"] and request.method == "POST":
      self._add_group(json.loads(request.content)["name"], None)
      return httpx.Response(201)
    if parts[0] == "groups" and len(parts) == 3 and parts[2] == "children":
      if request.method == "POST":
        name = json.loads(request.content)["name"]
        if any(g["name"] == name and g["parent"] == parts[1] for g in self.groups.values()):
          return httpx.Response(409)
        self._add_group(name, parts[1])
        return httpx.Response(201)
      return httpx.Response(200, json=[self._view(g) for g in self.groups.values() if g["parent"] == parts[1]])
    if parts[0] == "groups" and len(parts) == 3 and parts[2] == "members":
      return httpx.Response(200, json=[{"id": u, "username": self.users[u]["username"], "email": self.users[u]["email"]} for u in self.members[parts[1]]])
    if parts[0] == "groups" and len(parts) == 2 and request.method == "DELETE":
      del self.groups[parts[1]]
      return httpx.Response(204)
    if parts == ["users"]:
      return httpx.Response(200, json=[{"id": uid, **user} for uid, user in self.users.items() if user["email"] == params["email"]])
    if parts[0] == "users" and parts[2] == "groups":
      if request.method == "PUT":
        self.members[parts[3]].add(parts[1])
      else:
        self.members[parts[3]].discard(parts[1])
      return httpx.Response(204)
    return httpx.Response(404)

  def _root(self, group):
    while group["parent"]:
      group = self.groups[group["parent"]]
    return group

  def _view(self, group):
    return {"id": group["id"], "name": group["name"], "path": group["path"]}


@pytest.fixture
def keycloak():
  keycloak = FakeKeycloak()
  keycloak.add_user("dev", "dev@example.com")
  return keycloak


@pytest.fixture
def journal_path(tmp_path):
  return tmp_path / "journal.jsonl"


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def client(keycloak, journal_path, tokens):
  teams = KeycloakTeams("http://keycloak", "secret", transport=httpx.MockTransport(keycloak.handler))
  client = TestClient(create_app(FakeState(), Journal(journal_path), tokens.verifier(), teams=teams))
  client.headers["Authorization"] = f"Bearer {tokens.issue(sub='admin-1', groups=['platform-admins'])}"
  return client


@pytest.fixture
def user(tokens):
  return {"Authorization": f"Bearer {tokens.issue()}"}


def test_create_team_creates_group_under_teams(client, keycloak):
  response = client.post("/v1/teams", json={"name": "team-alpha"})
  assert response.status_code == 201
  assert response.json() == {"name": "team-alpha", "members": []}
  assert keycloak.group_by_path("/teams/team-alpha")
  assert client.get("/v1/teams").json() == {"items": [{"name": "team-alpha"}]}


def test_list_without_teams_parent_is_empty(client, keycloak):
  assert client.get("/v1/teams").json() == {"items": []}
  assert keycloak.group_by_path("/teams") is None


def test_create_duplicate_team_is_conflict(client):
  client.post("/v1/teams", json={"name": "team-alpha"})
  assert client.post("/v1/teams", json={"name": "team-alpha"}).status_code == 409


@pytest.mark.parametrize("name", ["platform-admins", "platform-users", "teams"])
def test_reserved_names_are_refused(client, name):
  assert client.post("/v1/teams", json={"name": name}).status_code == 422


def test_name_of_another_group_is_refused(client, keycloak):
  keycloak._add_group("ops", None)
  response = client.post("/v1/teams", json={"name": "ops"})
  assert response.status_code == 409
  assert "already a platform group" in response.json()["error"]["message"]


@pytest.mark.parametrize("name", ["Team", "team_alpha", "a" * 64, "team-\n"])
def test_invalid_names_are_refused(client, name):
  assert client.post("/v1/teams", json={"name": name}).status_code == 422


def test_members_add_list_remove(client, keycloak, journal_path):
  client.post("/v1/teams", json={"name": "team-alpha"})
  assert client.post("/v1/teams/team-alpha/members", json={"email": "dev@example.com"}).status_code == 201
  assert client.get("/v1/teams/team-alpha").json()["members"] == [{"email": "dev@example.com", "username": "dev"}]
  assert client.delete("/v1/teams/team-alpha/members/dev@example.com").status_code == 204
  assert client.get("/v1/teams/team-alpha").json()["members"] == []
  actions = [entry["action"] for entry in map(json.loads, journal_path.read_text().splitlines()) if "action" in entry]
  assert actions == ["create", "member-add", "member-remove"]


def test_add_unknown_user_is_not_found(client):
  client.post("/v1/teams", json={"name": "team-alpha"})
  response = client.post("/v1/teams/team-alpha/members", json={"email": "nobody@example.com"})
  assert response.status_code == 404
  assert "log in to the platform once" in response.json()["error"]["message"]


@pytest.mark.parametrize("accounts", [
  [("squatter", "victim@example.com", False)],
  [("one", "victim@example.com", True), ("two", "victim@example.com", True)],
])
def test_add_refuses_unverified_or_ambiguous_email(client, keycloak, accounts):
  for username, email, verified in accounts:
    keycloak.add_user(username, email, verified)
  client.post("/v1/teams", json={"name": "team-alpha"})
  assert client.post("/v1/teams/team-alpha/members", json={"email": "victim@example.com"}).status_code == 404
  assert client.get("/v1/teams/team-alpha").json()["members"] == []


def test_remove_takes_out_the_listed_account(client, keycloak):
  # A member added outside the API (Keycloak console) with an unverified e-mail, next to a verified
  # account with the same e-mail that is not in the team: the listed one is the one removed.
  keycloak.add_user("console-added", "shared@example.com", verified=False)
  keycloak.add_user("verified", "shared@example.com", verified=True)
  client.post("/v1/teams", json={"name": "team-alpha"})
  team = keycloak.group_by_path("/teams/team-alpha")["id"]
  listed = next(uid for uid, user in keycloak.users.items() if user["username"] == "console-added")
  keycloak.members[team].add(listed)
  assert client.delete("/v1/teams/team-alpha/members/Shared@Example.com").status_code == 204
  assert client.get("/v1/teams/team-alpha").json()["members"] == []


def test_remove_non_member_is_not_found(client):
  client.post("/v1/teams", json={"name": "team-alpha"})
  assert client.delete("/v1/teams/team-alpha/members/dev@example.com").status_code == 404


def test_unknown_team_is_not_found(client):
  assert client.get("/v1/teams/missing").status_code == 404
  assert client.delete("/v1/teams/missing").status_code == 404
  assert client.post("/v1/teams/missing/members", json={"email": "dev@example.com"}).status_code == 404


def test_team_shared_by_an_environment_cannot_be_deleted(client, keycloak, tokens):
  client.post("/v1/teams", json={"name": "team-alpha"})
  owner = {"Authorization": f"Bearer {tokens.issue(group_paths=['/platform-users', '/teams/team-alpha'])}"}
  client.post("/v1/environments", json={"name": "env-a", "profile": "ephemeral", "sharedWith": ["team-alpha"]}, headers=owner)
  response = client.delete("/v1/teams/team-alpha")
  assert response.status_code == 409
  assert "env-a" in response.json()["error"]["message"]
  assert keycloak.group_by_path("/teams/team-alpha")
  client.delete("/v1/environments/env-a/shares/team-alpha", headers=owner)
  assert client.delete("/v1/teams/team-alpha").status_code == 204


def test_delete_team(client, keycloak):
  client.post("/v1/teams", json={"name": "team-alpha"})
  assert client.delete("/v1/teams/team-alpha").status_code == 204
  assert keycloak.group_by_path("/teams/team-alpha") is None


def test_users_read_but_do_not_write(client, user, journal_path):
  client.post("/v1/teams", json={"name": "team-alpha"})
  assert client.get("/v1/teams", headers=user).status_code == 200
  assert client.get("/v1/teams/team-alpha", headers=user).status_code == 200
  assert client.post("/v1/teams", json={"name": "team-beta"}, headers=user).status_code == 403
  assert client.delete("/v1/teams/team-alpha", headers=user).status_code == 403
  assert client.post("/v1/teams/team-alpha/members", json={"email": "dev@example.com"}, headers=user).status_code == 403
  assert client.delete("/v1/teams/team-alpha/members/dev@example.com", headers=user).status_code == 403
  assert len(journal_path.read_text().splitlines()) == 2  # only the admin's create, recorded and applied


def test_admin_token_is_reused(client, keycloak):
  client.get("/v1/teams")
  client.get("/v1/teams")
  assert keycloak.token_requests == 1


def test_keycloak_failure_is_unavailable(client, keycloak):
  keycloak.fail_with = 500
  response = client.get("/v1/teams")
  assert response.status_code == 503
  assert response.json()["error"]["code"] == "unavailable"


def test_without_admin_client_teams_are_unavailable(journal_path, tokens):
  client = TestClient(create_app(FakeState(), Journal(journal_path), tokens.verifier()))
  response = client.get("/v1/teams", headers={"Authorization": f"Bearer {tokens.issue()}"})
  assert response.status_code == 503
  assert "no Keycloak admin client" in response.json()["error"]["message"]
