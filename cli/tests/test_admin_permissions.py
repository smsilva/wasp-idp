import json

import httpx

from wasp_platform.bootstrap.admin_permissions import ALL_GROUP_SCOPES, AdminPermissions, permissions


class FakeKeycloak:
  """Just the admin API calls AdminPermissions makes, with a call log."""

  def __init__(self):
    self.enabled = False
    self.groups = {"platform-admins": "g-admins", "platform-users": "g-users"}
    self.roles = [{"id": "r1", "name": "manage-users"}, {"id": "r2", "name": "view-users"}, {"id": "r3", "name": "query-groups"}]
    self.policies = {}
    self.permissions = {}
    # Realm users by e-mail (with their emailVerified and Google link userName) and the group ids each one belongs to.
    self.users = {}
    self.memberships = {}
    self.calls = []

  def handler(self, request: httpx.Request) -> httpx.Response:
    path = request.url.path.removeprefix("/admin/realms/platform")
    method = request.method
    self.calls.append((method, path))
    body = json.loads(request.content) if request.headers.get("content-type") == "application/json" else None
    if path.endswith("/protocol/openid-connect/token"):
      return httpx.Response(200, json={"access_token": "t"})
    if path == "":
      if method == "PUT":
        self.enabled = body["adminPermissionsEnabled"]
        return httpx.Response(204)
      return httpx.Response(200, json={"adminPermissionsEnabled": self.enabled})
    if path == "/groups":
      if method == "POST":
        self.groups[body["name"]] = f"g-{body['name']}"
        return httpx.Response(201)
      return httpx.Response(200, json=[{"id": gid, "name": name} for name, gid in self.groups.items()])
    if path == "/clients":
      return httpx.Response(200, json=[{"id": f"c-{request.url.params['clientId']}", "clientId": request.url.params["clientId"]}])
    if path.endswith("/service-account-user"):
      return httpx.Response(200, json={"id": "sa"})
    if path == "/users":
      email = request.url.params["email"]
      user = self.users.get(email)
      return httpx.Response(200, json=[{"id": f"u-{email}", "email": email, "emailVerified": user["verified"]}] if user else [])
    if path.startswith("/users/u-") and path.endswith("/federated-identity"):
      google = self.users[path.split("/")[2].removeprefix("u-")]["google"]
      return httpx.Response(200, json=[{"identityProvider": "google", "userName": google}] if google else [])
    if path.startswith("/users/u-") and "/groups" in path:
      user_id = path.split("/")[2]
      if method == "PUT":
        self.memberships.setdefault(user_id, set()).add(path.rsplit("/", 1)[1])
        return httpx.Response(204)
      return httpx.Response(200, json=[{"id": gid, "path": f"/{name}"} for name, gid in self.groups.items() if gid in self.memberships.get(user_id, set())])
    if path.startswith("/users/sa/role-mappings"):
      if method == "DELETE":
        removed = {role["name"] for role in body}
        self.roles = [role for role in self.roles if role["name"] not in removed]
        return httpx.Response(204)
      return httpx.Response(200, json=self.roles)
    server = "/clients/c-admin-permissions/authz/resource-server"
    if path == f"{server}/policy":
      return httpx.Response(200, json=[p for p in self.policies.values() if p["name"] == request.url.params["name"]])
    if path == f"{server}/policy/client":
      self.policies[body["name"]] = {**body, "id": f"p-{body['name']}"}
      return httpx.Response(201, json=self.policies[body["name"]])
    if path == f"{server}/permission":
      return httpx.Response(200, json=[p for p in self.permissions.values() if p["name"] == request.url.params["name"]])
    if path.startswith(f"{server}/permission/scope"):
      self.permissions[body["name"]] = {**body, "id": body.get("id") or f"perm-{body['name']}"}
      return httpx.Response(201)
    return httpx.Response(404)


def apply(keycloak, admins=(), log=lambda message: None):
  AdminPermissions("http://keycloak", "admin", "secret", transport=httpx.MockTransport(keycloak.handler)).apply(log, admins)


def test_apply_enables_creates_teams_and_drops_broad_roles():
  keycloak = FakeKeycloak()
  apply(keycloak)
  assert keycloak.enabled
  assert "teams" in keycloak.groups
  assert {role["name"] for role in keycloak.roles} == {"view-users", "query-groups"}
  assert keycloak.policies["platform-api-admin-client"]["logic"] == "POSITIVE"
  assert keycloak.policies["platform-api-admin-client-deny"]["logic"] == "NEGATIVE"
  deny = keycloak.permissions["platform-api-admin-platform-groups-deny"]
  assert deny["resources"] == ["g-admins", "g-users"] and deny["policies"] == ["p-platform-api-admin-client-deny"]


def test_apply_twice_changes_nothing_new():
  keycloak = FakeKeycloak()
  apply(keycloak)
  keycloak.calls.clear()
  apply(keycloak)
  writes = [call for call in keycloak.calls if call[0] in ("POST", "DELETE") and "token" not in call[1]]
  assert writes == []
  assert len(keycloak.permissions) == 3


def test_the_client_never_manages_members_nor_platform_groups():
  granted = permissions("allow", "deny", ["g-admins", "g-users"])
  allowed = [p for p in granted if p["policies"] == ["allow"]]
  assert all("manage-members" not in p["scopes"] and "impersonate-members" not in p["scopes"] for p in allowed)
  deny = next(p for p in granted if p["policies"] == ["deny"])
  assert deny["resources"] == ["g-admins", "g-users"] and set(deny["scopes"]) == set(ALL_GROUP_SCOPES)


def test_an_existing_admin_joins_platform_admins_once():
  keycloak = FakeKeycloak()
  keycloak.users = {"ana@example.com": {"verified": True, "google": "Ana@example.com"}}
  keycloak.memberships = {"u-ana@example.com": {"g-users"}}
  notes = []
  apply(keycloak, ["ana@example.com"], notes.append)
  assert keycloak.memberships["u-ana@example.com"] == {"g-users", "g-admins"}
  assert "added ana@example.com to platform-admins" in notes
  keycloak.calls.clear()
  apply(keycloak, ["ana@example.com"])
  assert not [call for call in keycloak.calls if call[0] == "PUT" and "/users/" in call[1]]


def test_an_admin_not_yet_signed_in_is_left_to_the_mapper():
  keycloak = FakeKeycloak()
  apply(keycloak, ["new@example.com"])
  assert keycloak.memberships == {}
  assert ("GET", "/users") in keycloak.calls


def test_a_user_who_only_typed_the_admin_email_is_not_promoted():
  keycloak = FakeKeycloak()
  keycloak.users = {
    "typed@example.com": {"verified": True, "google": "someone-else@gmail.com"},
    "local@example.com": {"verified": True, "google": None},
    "unverified@example.com": {"verified": False, "google": "unverified@example.com"},
  }
  apply(keycloak, list(keycloak.users))
  assert keycloak.memberships == {}
