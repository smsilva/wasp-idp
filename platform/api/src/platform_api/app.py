import os
import re
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import catalog, catalog_import, credentials as personal, environments, templates, teams as team_routes
from .auth import Principal, Verifier, current_principal
from .durations import expires_at, parse_duration
from .journal import Journal
from .state import ENVIRONMENTS, AlreadyExists, Conflict, NotFound

# k3d caps cluster names at 32 characters and the local provider prefixes "env-".
NAME_PATTERN = re.compile(r"^[a-z]([-a-z0-9]{0,26}[a-z0-9])?$")


class EnvironmentRequest(BaseModel):
  name: str
  profile: Literal["ephemeral", "shared"]
  expires: str | None = None
  sharedWith: list[str] = []

  @field_validator("sharedWith")
  @classmethod
  def check_teams(cls, value: list[str]) -> list[str]:
    for team in value:
      if not team_routes.LABEL.fullmatch(team):
        raise ValueError(f"'{team}' is not a team name")
    return value

  @field_validator("name")
  @classmethod
  def check_name(cls, value: str) -> str:
    if not NAME_PATTERN.fullmatch(value):
      raise ValueError("lowercase letters, digits and '-', starting with a letter, at most 28 characters")
    return value

  @field_validator("expires")
  @classmethod
  def check_expires(cls, value: str | None) -> str | None:
    if value is not None:
      parse_duration(value)
    return value


# Capabilities and whether a provider serves them, in the vocabulary of the CRD conditions (ADR 0022).
CAPABILITIES = {
  "identity": "Active",
  "environment": "Active",
  "catalog": "Active",
  "build": "NoProviderForCapability",
  "release": "NoProviderForCapability",
}

ERROR_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict", 422: "invalid_request", 503: "unavailable"}


def _error(status: int, message, headers=None, plan: dict | None = None) -> JSONResponse:
  body = {"code": ERROR_CODES.get(status, "error"), "message": message}
  if plan is not None:
    body["plan"] = plan
  return JSONResponse({"error": body}, status, headers=headers)


def create_app(state, journal: Journal, verifier: Verifier, allowed_hosts: list[str] | None = None, teams=None, credentials=None) -> FastAPI:
  app = FastAPI(title="Platform API", version="0.2.0")
  app.state.verifier = verifier
  if allowed_hosts:
    # Defense in depth next to the JWT: a web page that rebinds its own DNS name to 127.0.0.1 would
    # otherwise reach the API as a same-origin caller.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

  # One error shape for every route: {"error": {"code", "message"}}.
  @app.exception_handler(StarletteHTTPException)
  def http_error(request: Request, error: StarletteHTTPException):
    return _error(error.status_code, error.detail, getattr(error, "headers", None))

  @app.exception_handler(catalog_import.PlanRejected)
  def plan_rejected(request: Request, error: catalog_import.PlanRejected):
    return _error(error.status, error.message, plan=error.plan)

  @app.exception_handler(RequestValidationError)
  def validation_error(request: Request, error: RequestValidationError):
    message = "; ".join(f"{'.'.join(str(part) for part in item['loc'][1:])}: {item['msg']}" for item in error.errors())
    return _error(422, message)

  @app.get("/healthz")
  def healthz():
    return {"status": "ok"}

  @app.get("/v1/me")
  def me(principal: Principal = Depends(current_principal)):
    return {"sub": principal.sub, "email": principal.email, "groups": sorted([*principal.groups, *principal.teams]), "teams": sorted(principal.teams)}

  @app.get("/v1/capabilities")
  def capabilities(principal: Principal = Depends(current_principal)):
    return {"items": [{"name": name, "status": status} for name, status in CAPABILITIES.items()]}

  @app.post("/v1/environments", status_code=202)
  def create_environment(request: EnvironmentRequest, principal: Principal = Depends(current_principal)):
    deadline = expires_at(request.expires) if request.expires else None
    check_share(request.sharedWith, principal)
    body = environments.manifest(request.name, request.profile, deadline, principal.sub, principal.email, request.sharedWith)
    entry = journal.record("create", "Environment", request.name, body["spec"], principal.actor)
    try:
      created = state.create(ENVIRONMENTS, body)
    except AlreadyExists:
      raise HTTPException(409, f"environment '{request.name}' already exists")
    journal.mark_applied(entry)
    # Until a provider claims it, the request waits as a standard condition. The replace carries the
    # resourceVersion from the create: if a provider already touched the object, it owns the status.
    created["status"] = environments.no_provider_status()
    try:
      created = state.replace_status(ENVIRONMENTS, created)
    except Conflict:
      created = state.get(ENVIRONMENTS, request.name)
    return environments.view(created)

  @app.get("/v1/environments")
  def list_environments(all: bool = False, principal: Principal = Depends(current_principal)):
    # By default: mine and the ones shared with my teams; admins see every environment (ADR 0026).
    everything = all or environments.ADMIN_GROUP in principal.groups
    items = sorted(state.list(ENVIRONMENTS), key=lambda obj: obj["metadata"]["name"])
    return {"items": [environments.view(obj) for obj in items if everything or environments.can_use(obj, principal)]}

  @app.get("/v1/environments/{name}")
  def get_environment(name: str, principal: Principal = Depends(current_principal)):
    try:
      obj = state.get(ENVIRONMENTS, name)
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")
    # The personal kubeconfig holds no credential: kubectl asks /credentials for one (ADR 0028).
    return environments.view(obj, kubeconfig=personal.personal_kubeconfig(obj) if environments.can_use(obj, principal) else None)

  def usable(name: str, principal: Principal) -> dict:
    try:
      obj = state.get(ENVIRONMENTS, name)
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")
    if not environments.can_use(obj, principal):
      raise HTTPException(403, f"environment '{name}' is not yours nor shared with your teams")
    if not (obj.get("status") or {}).get("kubeconfigData"):
      raise HTTPException(409, f"environment '{name}' is not ready yet")
    return obj

  @app.post("/v1/environments/{name}/credentials")
  def issue_credential(name: str, principal: Principal = Depends(current_principal)):
    obj = usable(name, principal)
    if credentials is None:
      raise HTTPException(503, "personal credentials are not configured in the Platform API")
    try:
      return credentials.issue(obj, principal.sub, principal.email)
    except personal.VclusterUnavailable as error:
      raise HTTPException(503, str(error))

  @app.get("/v1/environments/{name}/admin-kubeconfig")
  def admin_kubeconfig(name: str, principal: Principal = Depends(current_principal)):
    # The vcluster's own admin credential: a certificate that cannot be revoked, so admins only.
    if environments.ADMIN_GROUP not in principal.groups:
      raise HTTPException(403, "the admin kubeconfig is only for platform-admins")
    obj = usable(name, principal)
    return {"name": name, "kubeconfigData": obj["status"]["kubeconfigData"]}

  @app.delete("/v1/environments/{name}", status_code=202)
  def delete_environment(name: str, principal: Principal = Depends(current_principal)):
    try:
      obj = state.get(ENVIRONMENTS, name)
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")
    if not environments.is_owner_or_admin(obj, principal):
      raise HTTPException(403, f"environment '{name}' can only be deleted by its owner or platform-admins")
    entry = journal.record("delete", "Environment", name, None, principal.actor)
    try:
      state.delete(ENVIRONMENTS, name, uid=obj["metadata"].get("uid"))
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")
    except Conflict:
      raise HTTPException(409, f"environment '{name}' changed while deleting: try again")
    journal.mark_applied(entry)
    return {"name": name, "status": "deleting"}

  def check_share(added: list[str], principal: Principal) -> None:
    """The owner shares only with their own teams; other teams need an admin. Membership is checked
    before existence, so a non-member cannot probe which teams exist."""
    if not added:
      return
    admin = environments.ADMIN_GROUP in principal.groups
    foreign = sorted(set(added) - set(principal.teams))
    if foreign and not admin:
      raise HTTPException(403, f"you can only share with teams you are a member of: {', '.join(foreign)}")
    if teams is None:
      raise HTTPException(503, "teams are not configured: the Platform API has no Keycloak admin client")
    try:
      known = set(teams.names())
    except team_routes.TeamsUnavailable as error:
      raise HTTPException(503, str(error))
    missing = sorted(set(added) - known)
    if missing:
      raise HTTPException(422, f"team not found: {', '.join(missing)}")

  def change_share(name: str, team: str, principal: Principal, add: bool) -> dict:
    try:
      obj = state.get(ENVIRONMENTS, name)
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")
    if not environments.is_owner_or_admin(obj, principal):
      raise HTTPException(403, f"environment '{name}' can only be shared by its owner or platform-admins")
    current = environments.shared_with(obj)
    if add:
      check_share([team], principal)
      if team in current:
        return environments.view(obj)
      updated = sorted({*current, team})
    else:
      # No membership check: taking access away is always allowed to the owner, even for a deleted team.
      if team not in current:
        raise HTTPException(404, f"environment '{name}' is not shared with '{team}'")
      updated = [item for item in current if item != team]
    spec = {key: value for key, value in obj["spec"].items() if key != "sharedWith"}
    if updated:
      spec["sharedWith"] = updated
    obj["spec"] = spec
    entry = journal.record("share" if add else "unshare", "Environment", name, {"team": team}, principal.actor)
    try:
      replaced = state.replace(ENVIRONMENTS, obj)
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")
    except Conflict:
      raise HTTPException(409, f"environment '{name}' changed while sharing: try again")
    journal.mark_applied(entry)
    if not add:
      # Whoever still has access through another team gets a new token on the next kubectl call.
      owner = (replaced["metadata"].get("annotations") or {}).get(environments.OWNER_ANNOTATION)
      personal.revoke_quietly(credentials, replaced, keep={personal.identity_name(owner)} if owner else set())
    return environments.view(replaced)

  @app.put("/v1/environments/{name}/shares/{team}")
  def share_environment(name: str, team: str, principal: Principal = Depends(current_principal)):
    if not team_routes.LABEL.fullmatch(team):
      raise HTTPException(422, f"'{team}' is not a team name")
    return change_share(name, team, principal, add=True)

  @app.delete("/v1/environments/{name}/shares/{team}")
  def unshare_environment(name: str, team: str, principal: Principal = Depends(current_principal)):
    return change_share(name, team, principal, add=False)

  # Before the catalog router: its /{plural} routes would otherwise take "import" and "templates" as kinds.
  app.include_router(catalog_import.router(state, journal, teams))
  app.include_router(templates.router(state, journal, teams))
  app.include_router(catalog.router(state, journal, teams))
  app.include_router(team_routes.router(teams, journal, state, credentials))
  return app


def build() -> FastAPI:
  from .state import KubeApplyWriter

  namespace = os.environ.get("PLATFORM_NAMESPACE", "platform-system")
  journal_path = os.environ.get("PLATFORM_JOURNAL", "/var/lib/platform/journal.jsonl")
  allowed_hosts = os.environ.get("PLATFORM_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
  verifier = Verifier(issuer=os.environ["PLATFORM_OIDC_ISSUER"], jwks_url=os.environ["PLATFORM_OIDC_JWKS_URL"])
  # Without the admin client the API still serves everything else; /v1/teams answers 503.
  admin_secret = os.environ.get("PLATFORM_KEYCLOAK_ADMIN_SECRET")
  teams = team_routes.KeycloakTeams(os.environ["PLATFORM_KEYCLOAK_URL"], admin_secret) if admin_secret else None
  credentials = personal.VclusterCredentials(os.environ.get("PLATFORM_VCLUSTER_SERVER", personal.SERVER))
  return create_app(KubeApplyWriter(namespace), Journal(journal_path), verifier, allowed_hosts, teams, credentials)
