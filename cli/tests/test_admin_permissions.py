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


def apply(keycloak):
  AdminPermissions("http://keycloak", "admin", "secret", transport=httpx.MockTransport(keycloak.handler)).apply(lambda message: None)


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
