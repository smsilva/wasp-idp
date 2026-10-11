"""Builds and the version index (#206, ADR 0030): a branch becomes a version, without waiting for a merge.

The platform does not build: it writes a Build, and the scm_github provider dispatches the repo's
platform-build workflow on GitHub Actions, follows the run, validates app-spec.yaml (Score) and
registers the version. The version index is a read mirror, never changed here at a user's request.
The App, not the person, dispatches and reads the repo, so GitHub does not decide who builds: only
members of the component's owner team and platform-admins create a build. Reading builds and versions
stays open to any signed-in user, like the component index.
"""
import re
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from .auth import Principal, current_principal
from .catalog import CREATED_BY_ANNOTATION, LABEL
from .environments import ADMIN_GROUP
from .journal import Journal
from .scm import PLURAL as CONNECTIONS, status_of as connection_status
from .state import GROUP, VERSION, AlreadyExists, NotFound

BUILDS = "builds"
VERSIONS = "versions"
COMPONENTS = "components"
KIND = "Build"
# The same rule as the platform-build workflow: <major>.<minor>.<patch>[-<pre-release>].
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?")
# A git branch name, the part of git check-ref-format a branch can break.
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+-]{0,254}")


class BuildRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  component: str
  branch: str
  version: str | None = None

  @field_validator("component")
  @classmethod
  def check_component(cls, value: str) -> str:
    if not LABEL.fullmatch(value):
      raise ValueError("lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters")
    return value

  @field_validator("branch")
  @classmethod
  def check_branch(cls, value: str) -> str:
    if not BRANCH.fullmatch(value) or ".." in value or "//" in value or value.endswith(("/", ".", ".lock")):
      raise ValueError("not a git branch name")
    return value

  @field_validator("version")
  @classmethod
  def check_version(cls, value: str | None) -> str | None:
    if value is not None and not VERSION_PATTERN.fullmatch(value):
      raise ValueError("<major>.<minor>.<patch>[-<pre-release>], e.g. 1.0.0-rc.1")
    return value


def ready_of(obj: dict) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), None)


def build_view(obj: dict) -> dict:
  spec = obj.get("spec", {})
  status = obj.get("status") or {}
  ready = ready_of(obj)
  if ready is None:
    state = "pending"
  else:
    state = "ready" if ready.get("status") == "True" else ready.get("reason") or "pending"
  return {
    "kind": KIND,
    "name": obj["metadata"]["name"],
    "component": spec.get("component"),
    "branch": spec.get("branch"),
    "requestedVersion": spec.get("version"),
    "repo": spec.get("repo"),
    "requestId": spec.get("requestId"),
    "status": state,
    "runUrl": status.get("runUrl"),
    "commit": (status.get("result") or {}).get("commit") or (status.get("run") or {}).get("headSha"),
    "result": status.get("result"),
    "appSpec": status.get("appSpec"),
    "errors": status.get("errors") or [],
    "conditions": status.get("conditions") or [],
    "createdAt": obj["metadata"].get("creationTimestamp"),
  }


def version_view(obj: dict) -> dict:
  spec = obj.get("spec", {})
  return {
    "kind": "Version",
    "name": obj["metadata"]["name"],
    **{field: spec.get(field) for field in ("component", "version", "image", "digest", "commit", "branch", "createdAt", "build")},
  }


def router(state, journal: Journal) -> APIRouter:
  routes = APIRouter(prefix="/v1")

  def connection_of(component: str, repo: str) -> dict:
    """The connection of the repo's org: the one whose App can dispatch its workflows."""
    org = repo.split("/")[0]
    found = [obj for obj in state.list(CONNECTIONS) if ((obj.get("spec") or {}).get("github") or {}).get("org") == org]
    if not found:
      raise HTTPException(409, f"build of '{component}': no scm connection for the org '{org}'")
    ready = [obj for obj in found if connection_status(obj) == "ready"]
    if not ready:
      names = ", ".join(f"'{obj['metadata']['name']}' ({connection_status(obj)})" for obj in found)
      raise HTTPException(409, f"build of '{component}': scm connection {names} is not ready")
    return sorted(ready, key=lambda obj: obj["metadata"]["name"])[0]

  @routes.post("/builds", status_code=202)
  def create(request: BuildRequest, principal: Principal = Depends(current_principal)):
    try:
      component = state.get(COMPONENTS, request.component)
    except NotFound:
      raise HTTPException(422, f"build of '{request.component}': component not found")
    owner = (component.get("spec") or {}).get("owner")
    if not (owner in principal.teams or ADMIN_GROUP in principal.groups):
      raise HTTPException(403, f"build of '{request.component}': only members of its owner team ({owner or 'none'}) and {ADMIN_GROUP} build it")
    repo = ((component.get("spec") or {}).get("source") or {}).get("repo")
    if not repo or "/" not in repo:
      raise HTTPException(422, f"build of '{request.component}': the component has no repo in the index")
    if request.version is not None:
      # Refused before the dispatch: the CI would push the tag again, over the image the index points to.
      try:
        existing = state.get(VERSIONS, f"{request.component}.{request.version}".lower())
      except NotFound:
        existing = None
      if existing is not None:
        raise HTTPException(409, f"build of '{request.component}': version {existing['spec'].get('version')} is already in the index (commit {str(existing['spec'].get('commit'))[:7]})")
    connection = connection_of(request.component, repo)
    spec = {
      "component": request.component,
      "branch": request.branch,
      "requestId": str(uuid.uuid4()),
      "repo": repo,
      "scmConnection": connection["metadata"]["name"],
    }
    if request.version is not None:
      spec["version"] = request.version
    name = f"{request.component}-{secrets.token_hex(3)}"
    entry = journal.record("create", KIND, name, spec, principal.actor)
    body = {
      "apiVersion": f"{GROUP}/{VERSION}",
      "kind": KIND,
      "metadata": {"name": name, "annotations": {CREATED_BY_ANNOTATION: principal.sub}},
      "spec": spec,
    }
    try:
      created = state.create(BUILDS, body)
    except AlreadyExists:  # 3 random bytes taken by another build of the same component: try again
      raise HTTPException(409, f"build '{name}' already exists: try again")
    journal.mark_applied(entry)
    return build_view(created)

  @routes.get("/builds")
  def list_builds(component: str | None = None, principal: Principal = Depends(current_principal)):
    items = [build_view(obj) for obj in state.list(BUILDS) if component is None or obj["spec"].get("component") == component]
    return {"items": sorted(items, key=lambda item: (item["createdAt"] or "", item["name"]), reverse=True)}

  @routes.get("/builds/{name}")
  def get(name: str, principal: Principal = Depends(current_principal)):
    try:
      return build_view(state.get(BUILDS, name))
    except NotFound:
      raise HTTPException(404, f"build '{name}' not found")

  @routes.get("/versions")
  def list_versions(component: str | None = None, principal: Principal = Depends(current_principal)):
    items = [version_view(obj) for obj in state.list(VERSIONS) if component is None or obj["spec"].get("component") == component]
    return {"items": sorted(items, key=lambda item: (item["createdAt"] or "", item["name"]), reverse=True)}

  return routes
