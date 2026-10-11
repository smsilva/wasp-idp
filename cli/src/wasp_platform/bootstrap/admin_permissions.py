"""Fine-grained admin permissions (Keycloak v2) of the platform-api-admin client (#238, ADR 0026).

The client reads the realm through view-users, but writes only what teams need: groups (with
platform-admins and platform-users denied explicitly) and group memberships. What Keycloak 26.5
showed when this was designed:

- A permission on /teams does not reach its children, and the group listings only show groups with
  a permission of their own; so writes go on every group, and reads come from view-users.
- Adding a member needs manage-group-membership on the user as well as manage-membership on the group.
- manage-members is left out: it lets the holder edit members, credentials included.
- The policies match the client, not its service-account user: user policies never matched it.

keycloak-config-cli does not declare these, so init applies them through the admin API, as the
bootstrap admin, after every realm import. Every step is idempotent.
"""
import httpx

REALM = "platform"
CLIENT_ID = "platform-api-admin"
TEAMS = "teams"
PLATFORM_GROUPS = ("platform-admins", "platform-users")
# Roles of realm-management the client must not keep (an install from before #238 had manage-users).
BROAD_ROLES = {"manage-users", "manage-realm", "manage-clients", "manage-authorization", "realm-admin", "impersonation"}
ALLOW = f"{CLIENT_ID}-client"
DENY = f"{CLIENT_ID}-client-deny"
GROUP_SCOPES = ["view", "manage", "view-members", "manage-membership"]
ALL_GROUP_SCOPES = [*GROUP_SCOPES, "manage-members", "impersonate-members"]
USER_SCOPES = ["view", "manage-group-membership"]


def permissions(allow: str, deny: str, platform_group_ids: list[str]) -> list[dict]:
  """The scope permissions the client gets; resources [] means every resource of the type."""
  return [
    {"name": f"{CLIENT_ID}-groups", "resourceType": "Groups", "resources": [], "scopes": GROUP_SCOPES, "policies": [allow]},
    {"name": f"{CLIENT_ID}-platform-groups-deny", "resourceType": "Groups", "resources": platform_group_ids, "scopes": ALL_GROUP_SCOPES, "policies": [deny]},
    {"name": f"{CLIENT_ID}-users", "resourceType": "Users", "resources": [], "scopes": USER_SCOPES, "policies": [allow]},
  ]


class AdminPermissions:
  def __init__(self, keycloak_url: str, username: str, password: str, transport=None):
    self.http = httpx.Client(base_url=keycloak_url, timeout=30, transport=transport)
    token = self.http.post(
      "/realms/master/protocol/openid-connect/token",
      data={"grant_type": "password", "client_id": "admin-cli", "username": username, "password": password},
    )
    token.raise_for_status()
    self.http.headers["Authorization"] = f"Bearer {token.json()['access_token']}"

  def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
    response = self.http.request(method, f"/admin/realms/{REALM}{path}", **kwargs)
    response.raise_for_status()
    return response

  def _client(self, client_id: str) -> dict:
    return self._call("GET", "/clients", params={"clientId": client_id}).json()[0]

  def _top_groups(self) -> dict[str, str]:
    return {group["name"]: group["id"] for group in self._call("GET", "/groups", params={"max": "1000"}).json()}

  def apply(self, log) -> None:
    if not self._call("GET", "").json().get("adminPermissionsEnabled"):
      log("enabling fine-grained admin permissions …")
      self._call("PUT", "", json={"adminPermissionsEnabled": True})

    # /teams is created here, as the realm admin; the API creates only teams below it.
    if TEAMS not in self._top_groups():
      self._call("POST", "/groups", json={"name": TEAMS})
    groups = self._top_groups()

    api_client = self._client(CLIENT_ID)
    account = self._call("GET", f"/clients/{api_client['id']}/service-account-user").json()
    realm_management = self._client("realm-management")
    mappings = f"/users/{account['id']}/role-mappings/clients/{realm_management['id']}"
    broad = [role for role in self._call("GET", mappings).json() if role["name"] in BROAD_ROLES]
    if broad:
      log(f"removing {', '.join(sorted(role['name'] for role in broad))} from {CLIENT_ID} …")
      self._call("DELETE", mappings, json=broad)

    server = f"/clients/{self._client('admin-permissions')['id']}/authz/resource-server"
    allow = self._policy(server, ALLOW, api_client["id"], "POSITIVE")
    deny = self._policy(server, DENY, api_client["id"], "NEGATIVE")
    for permission in permissions(allow, deny, [groups[name] for name in PLATFORM_GROUPS]):
      body = {**permission, "decisionStrategy": "UNANIMOUS"}
      existing = self._named(f"{server}/permission", permission["name"])
      if existing:
        self._call("PUT", f"{server}/permission/scope/{existing['id']}", json={**body, "id": existing["id"]})
      else:
        self._call("POST", f"{server}/permission/scope", json=body)

  def _named(self, path: str, name: str) -> dict | None:
    return next((item for item in self._call("GET", path, params={"name": name}).json() if item["name"] == name), None)

  def _policy(self, server: str, name: str, client_uuid: str, logic: str) -> str:
    existing = self._named(f"{server}/policy", name)
    if existing:
      return existing["id"]
    return self._call("POST", f"{server}/policy/client", json={"name": name, "clients": [client_uuid], "logic": logic}).json()["id"]
