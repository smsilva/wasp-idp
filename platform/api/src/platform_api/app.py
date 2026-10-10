import os
import re
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, field_validator

from . import environments
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


def current_actor(request: Request) -> str:
  # TODO(#144): validate the Keycloak JWT and return the subject. No authentication in this slice:
  # the service is only reachable through 127.0.0.1 on the host.
  return "anonymous"


def create_app(state, journal: Journal, allowed_hosts: list[str] | None = None) -> FastAPI:
  app = FastAPI(title="Platform API", version="0.1.0")
  if allowed_hosts:
    # Without authentication (#144), "only on 127.0.0.1" must also hold for the Host header: a web page
    # that rebinds its own DNS name to 127.0.0.1 would otherwise reach the API as a same-origin caller.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

  @app.get("/healthz")
  def healthz():
    return {"status": "ok"}

  @app.post("/v1/environments", status_code=202)
  def create_environment(request: EnvironmentRequest, actor: str = Depends(current_actor)):
    deadline = expires_at(request.expires) if request.expires else None
    body = environments.manifest(request.name, request.profile, deadline)
    entry = journal.record("create", "Environment", request.name, body["spec"], actor)
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
  def list_environments():
    items = sorted(state.list(ENVIRONMENTS), key=lambda obj: obj["metadata"]["name"])
    return {"items": [environments.view(obj) for obj in items]}

  @app.get("/v1/environments/{name}")
  def get_environment(name: str):
    try:
      return environments.view(state.get(ENVIRONMENTS, name))
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")

  @app.delete("/v1/environments/{name}", status_code=202)
  def delete_environment(name: str, actor: str = Depends(current_actor)):
    try:
      state.get(ENVIRONMENTS, name)
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")
    entry = journal.record("delete", "Environment", name, None, actor)
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
  return create_app(KubeApplyWriter(namespace), Journal(journal_path), allowed_hosts)
