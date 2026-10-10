import os
import re
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import environments
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

  @field_validator("name")
  @classmethod
  def check_name(cls, value: str) -> str:
    if not NAME_PATTERN.match(value):
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
  "catalog": "NoProviderForCapability",
  "build": "NoProviderForCapability",
  "release": "NoProviderForCapability",
}

ERROR_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict", 422: "invalid_request"}


def _error(status: int, message, headers=None) -> JSONResponse:
  return JSONResponse({"error": {"code": ERROR_CODES.get(status, "error"), "message": message}}, status, headers=headers)


def create_app(state, journal: Journal, verifier: Verifier, allowed_hosts: list[str] | None = None) -> FastAPI:
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

  @app.exception_handler(RequestValidationError)
  def validation_error(request: Request, error: RequestValidationError):
    message = "; ".join(f"{'.'.join(str(part) for part in item['loc'][1:])}: {item['msg']}" for item in error.errors())
    return _error(422, message)

  @app.get("/healthz")
  def healthz():
    return {"status": "ok"}

  @app.get("/v1/me")
  def me(principal: Principal = Depends(current_principal)):
    return {"sub": principal.sub, "email": principal.email, "groups": sorted(principal.groups)}

  @app.get("/v1/capabilities")
  def capabilities(principal: Principal = Depends(current_principal)):
    return {"items": [{"name": name, "status": status} for name, status in CAPABILITIES.items()]}

  @app.post("/v1/environments", status_code=202)
  def create_environment(request: EnvironmentRequest, principal: Principal = Depends(current_principal)):
    deadline = expires_at(request.expires) if request.expires else None
    body = environments.manifest(request.name, request.profile, deadline, principal.sub)
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
  def list_environments(principal: Principal = Depends(current_principal)):
    items = sorted(state.list(ENVIRONMENTS), key=lambda obj: obj["metadata"]["name"])
    return {"items": [environments.view(obj) for obj in items]}

  @app.get("/v1/environments/{name}")
  def get_environment(name: str, principal: Principal = Depends(current_principal)):
    try:
      obj = state.get(ENVIRONMENTS, name)
      return environments.view(obj, with_kubeconfig=environments.can_read_credentials(obj, principal))
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")

  @app.delete("/v1/environments/{name}", status_code=202)
  def delete_environment(name: str, principal: Principal = Depends(current_principal)):
    try:
      state.get(ENVIRONMENTS, name)
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")
    entry = journal.record("delete", "Environment", name, None, principal.actor)
    try:
      state.delete(ENVIRONMENTS, name)
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")
    journal.mark_applied(entry)
    return {"name": name, "status": "deleting"}

  return app


def build() -> FastAPI:
  from .state import KubeApplyWriter

  namespace = os.environ.get("PLATFORM_NAMESPACE", "platform-system")
  journal_path = os.environ.get("PLATFORM_JOURNAL", "/var/lib/platform/journal.jsonl")
  allowed_hosts = os.environ.get("PLATFORM_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
  verifier = Verifier(issuer=os.environ["PLATFORM_OIDC_ISSUER"], jwks_url=os.environ["PLATFORM_OIDC_JWKS_URL"])
  return create_app(KubeApplyWriter(namespace), Journal(journal_path), verifier, allowed_hosts)
