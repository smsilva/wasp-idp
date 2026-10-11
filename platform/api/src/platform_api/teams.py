"""Teams (ADR 0026): Keycloak groups under /teams, owned by the Platform API.

The group is the source of truth for the team and its members: membership has to live in Keycloak
to reach the token (`groups` claim, without path), so there is no team CRD. The API reaches the
realm admin API with its own confidential client, platform-api-admin.
"""
import re
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator

from .auth import Principal, current_principal, require_group
from .environments import ADMIN_GROUP
from .journal import Journal
from .state import ENVIRONMENTS

PARENT = "teams"
# Like catalog names: the team is the `owner` of catalog entities (ADR 0023).
LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
# The `groups` claim has no path, so a team named like a platform group would grant its rights.
RESERVED = {PARENT, ADMIN_GROUP, "platform-users"}


class TeamNotFound(Exception):
  pass


class TeamExists(Exception):
  pass


class NameTaken(Exception):
  """A group outside /teams already has the name: in the token, both would read the same."""


class UserNotFound(Exception):
  pass


class NotMember(Exception):
  pass


class TeamsUnavailable(Exception):
  pass


class KeycloakTeams:
  def __init__(self, base_url: str, client_secret: str, realm: str = "platform", client_id: str = "platform-api-admin", transport=None):
    self.realm = realm
    self.client_id = client_id
    self.client_secret = client_secret
    self.http = httpx.Client(base_url=base_url, timeout=10, transport=transport)
    self._token = None
    self._token_expiry = 0.0

  def _access_token(self) -> str:
    if self._token and time.monotonic() < self._token_expiry:
      return self._token
    response = self._send("POST", f"/realms/{self.realm}/protocol/openid-connect/token", auth=False, data={
      "grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret,
    })
    body = response.json()
    self._token = body["access_token"]
    # Renew a little before Keycloak does, so a request never carries a token about to expire.
    self._token_expiry = time.monotonic() + max(body.get("expires_in", 60) - 15, 5)
    return self._token

  def _send(self, method: str, path: str, auth: bool = True, **kwargs) -> httpx.Response:
    headers = {"Authorization": f"Bearer {self._access_token()}"} if auth else {}
    try:
      response = self.http.request(method, path, headers=headers, **kwargs)
    except httpx.TransportError as error:
      raise TeamsUnavailable(f"Keycloak unreachable: {error}") from error
    if response.status_code in (401, 403) or response.status_code >= 500:
      raise TeamsUnavailable(f"Keycloak admin API answered {response.status_code} to {method} {path}")
    return response

  def _admin(self, method: str, path: str, **kwargs) -> httpx.Response:
    return self._send(method, f"/admin/realms/{self.realm}{path}", **kwargs)

  def _parent_id(self, create: bool = False) -> str | None:
    groups = self._admin("GET", "/groups", params={"search": PARENT, "exact": "true", "briefRepresentation": "true"}).json()
    found = next((group["id"] for group in groups if group.get("path") == f"/{PARENT}"), None)
    if found or not create:
      return found
    # Created on first use, never in realm-platform.yaml: keycloak-config-cli would prune the teams below it.
    self._admin("POST", "/groups", json={"name": PARENT})
    return self._parent_id()

  def _children(self) -> list[dict]:
    parent = self._parent_id()
    if not parent:
      return []
    return self._admin("GET", f"/groups/{parent}/children", params={"briefRepresentation": "true", "max": "1000"}).json()

  def _team_id(self, name: str) -> str:
    found = next((group["id"] for group in self._children() if group["name"] == name), None)
    if not found:
      raise TeamNotFound(name)
    return found

  def _user_id(self, email: str) -> str:
    # Membership grants access, so the e-mail must name exactly one account that proved it owns it:
    # an unverified e-mail is only a claim, and taking the first of several matches picks at random.
    users = self._admin("GET", "/users", params={"email": email, "exact": "true"}).json()
    verified = [user for user in users if user.get("emailVerified") and user.get("email", "").lower() == email.lower()]
    if len(verified) != 1:
      raise UserNotFound(email)
    return verified[0]["id"]

  def names(self) -> list[str]:
    return sorted(group["name"] for group in self._children())

  def _member_accounts(self, team: str) -> list[dict]:
    return self._admin("GET", f"/groups/{team}/members", params={"briefRepresentation": "true", "max": "1000"}).json()

  def members(self, name: str) -> list[dict]:
    users = self._member_accounts(self._team_id(name))
    return sorted(({"email": user.get("email"), "username": user["username"]} for user in users), key=lambda user: user["username"])

  def create(self, name: str) -> None:
    if name in self.names():
      raise TeamExists(name)
    if self._admin("GET", "/groups", params={"search": name, "exact": "true", "briefRepresentation": "true"}).json():
      raise NameTaken(name)
    response = self._admin("POST", f"/groups/{self._parent_id(create=True)}/children", json={"name": name})
    if response.status_code == 409:
      raise TeamExists(name)

  def delete(self, name: str) -> None:
    self._admin("DELETE", f"/groups/{self._team_id(name)}")

  def add_member(self, name: str, email: str) -> None:
    team = self._team_id(name)
    self._admin("PUT", f"/users/{self._user_id(email)}/groups/{team}")

  def remove_member(self, name: str, email: str) -> None:
    # Removes the accounts the team lists under this e-mail, not the one an e-mail lookup would pick:
    # what is checked and what is removed must be the same account. Taking access away needs no
    # verified e-mail, so every listed account with it goes.
    team = self._team_id(name)
    accounts = [user["id"] for user in self._member_accounts(team) if (user.get("email") or "").lower() == email.lower()]
    if not accounts:
      raise NotMember(email)
    for account in accounts:
      self._admin("DELETE", f"/users/{account}/groups/{team}")


def known_teams(teams) -> set[str]:
  """The names of the teams, for checks that need them all; 503 when Keycloak cannot answer."""
  if teams is None:
    raise HTTPException(503, "teams are not configured: the Platform API has no Keycloak admin client")
  try:
    return set(teams.names())
  except TeamsUnavailable as error:
    raise HTTPException(503, str(error))


def users_of(state, name: str) -> list[str]:
  """What refers to the team by name: environments shared with it and catalog entities it owns."""
  # Imported here: catalog imports this module for known_teams.
  from .catalog import KINDS

  found = [f"environment/{obj['metadata']['name']}" for obj in state.list(ENVIRONMENTS) if name in ((obj.get("spec") or {}).get("sharedWith") or [])]
  for kind in KINDS.values():
    found += [f"{kind.singular}/{obj['metadata']['name']}" for obj in state.list(kind.plural) if (obj.get("spec") or {}).get("owner") == name]
  return sorted(found)


class TeamRequest(BaseModel):
  name: str

  @field_validator("name")
  @classmethod
  def check_name(cls, value: str) -> str:
    if not LABEL.fullmatch(value):
      raise ValueError("lowercase letters, digits and '-', at most 63 characters")
    if value in RESERVED:
      raise ValueError(f"'{value}' is reserved by the platform")
    return value


class MemberRequest(BaseModel):
  email: str


def router(teams, journal: Journal, state=None) -> APIRouter:
  routes = APIRouter(prefix="/v1/teams")
  admin = require_group(ADMIN_GROUP)

  def directory():
    if teams is None:
      raise HTTPException(503, "teams are not configured: the Platform API has no Keycloak admin client")
    return teams

  def call(function, *args):
    try:
      return function(*args)
    except TeamNotFound as error:
      raise HTTPException(404, f"team '{error}' not found")
    except TeamExists as error:
      raise HTTPException(409, f"team '{error}' already exists")
    except NameTaken as error:
      raise HTTPException(409, f"'{error}' is already a platform group: pick another team name")
    except UserNotFound as error:
      raise HTTPException(404, f"user '{error}' not found: they must log in to the platform once first, with a verified e-mail")
    except NotMember as error:
      raise HTTPException(404, f"'{error}' is not a member of the team")
    except TeamsUnavailable as error:
      raise HTTPException(503, str(error))

  @routes.get("")
  def list_teams(principal: Principal = Depends(current_principal)):
    return {"items": [{"name": name} for name in call(directory().names)]}

  @routes.post("", status_code=201)
  def create(request: TeamRequest, principal: Principal = Depends(admin)):
    entry = journal.record("create", "Team", request.name, None, principal.actor)
    call(directory().create, request.name)
    journal.mark_applied(entry)
    return {"name": request.name, "members": []}

  @routes.get("/{name}")
  def get(name: str, principal: Principal = Depends(current_principal)):
    return {"name": name, "members": call(directory().members, name)}

  @routes.delete("/{name}", status_code=204)
  def delete(name: str, principal: Principal = Depends(admin)):
    # Environments and catalog entities keep the team by name: a team recreated with the same name
    # would inherit them, so they go first. Not atomic, like the catalog's dependents check.
    if state is not None:
      found = users_of(state, name)
      if found:
        raise HTTPException(409, f"team '{name}' is still in use: {', '.join(found)}; unshare or change the owner first")
    entry = journal.record("delete", "Team", name, None, principal.actor)
    call(directory().delete, name)
    journal.mark_applied(entry)
    return Response(status_code=204)

  @routes.post("/{name}/members", status_code=201)
  def add_member(name: str, request: MemberRequest, principal: Principal = Depends(admin)):
    entry = journal.record("member-add", "Team", name, {"email": request.email}, principal.actor)
    call(directory().add_member, name, request.email)
    journal.mark_applied(entry)
    return {"team": name, "email": request.email}

  @routes.delete("/{name}/members/{email}", status_code=204)
  def remove_member(name: str, email: str, principal: Principal = Depends(admin)):
    entry = journal.record("member-remove", "Team", name, {"email": email}, principal.actor)
    call(directory().remove_member, name, email)
    journal.mark_applied(entry)
    return Response(status_code=204)

  return routes
