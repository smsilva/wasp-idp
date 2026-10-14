"""Components (ADR 0023, #204): created through the golden path, read from the index.

A component lives in its repo's catalog-info.yaml. The platform creates the repo (a ComponentCreation,
run by the scm_github provider) and indexes what it created; the index is a read mirror, never
changed here at a user's request.
"""
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from wasp_templates.source import SourceError, coerce

from .auth import Principal, current_principal
from .catalog import CREATED_BY_ANNOTATION, DESCRIPTION_MAX, LABEL
from .durations import format_time
from .environments import ADMIN_GROUP, can_use, is_owner_or_admin
from .journal import Journal, redacted
from .scm import PLURAL as CONNECTIONS, status_of as connection_status
from .state import CATALOG_GROUP, ENVIRONMENTS, GROUP, VERSION, AlreadyExists, Conflict, NotFound
from .teams import known_teams
from .templates import TYPES
from .workloads import INSTANCES, ready_of as instance_ready

COMPONENTS = "components"
CREATIONS = "componentcreations"
CREATION_KIND = "ComponentCreation"
PRD_MAX = 64 * 1024
# The provider's steps, FINAL reasons and retention (STEPS, FINAL and RETENTION in
# platform/providers/scm_github/src/scm_github_provider/component_creation.py): this API is a separate
# uv project, so it keeps a copy, and a provider test fails when they differ.
STEPS = ("Validated", "Rendered", "RepoCreated", "Pushed", "Protected", "Registered")
# Ready=False with these reasons is a stopped creation: it holds the name until RETENTION removes it,
# or until create --replace or creation delete. The CLI's FINAL also has the connection reasons, which
# the provider retries: those creations are still running.
FINAL = {"RepoAlreadyExists", "RepoGone", "ComponentExists", "GitHubRejected"}
RETENTION = timedelta(hours=24)


class ComponentRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  name: str
  system: str
  owner: str | None = None
  description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
  type: Literal["service", "website", "library"] | None = None
  template: str | None = None
  params: dict = Field(default_factory=dict)
  scm: str | None = None
  visibility: Literal["public", "private"] | None = None
  prd: str | None = Field(default=None, max_length=PRD_MAX)
  # Takes the place of a stopped creation (FINAL) with the same name; never of a running or Ready one.
  replace: bool = False

  @field_validator("name", "system", "owner", "template", "scm")
  @classmethod
  def check_label(cls, value: str | None) -> str | None:
    if value is not None and not LABEL.fullmatch(value):
      raise ValueError("lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters")
    return value


def component_view(obj: dict) -> dict:
  spec = obj.get("spec", {})
  source = spec.get("source") or {}
  return {
    "kind": "Component",
    "name": obj["metadata"]["name"],
    "system": spec.get("system"),
    "owner": spec.get("owner"),
    "type": spec.get("type"),
    "lifecycle": spec.get("lifecycle"),
    "description": spec.get("description"),
    "repo": source.get("repo"),
    "template": source.get("template"),
    "origin": source.get("origin"),
    "createdAt": obj["metadata"].get("creationTimestamp"),
  }


def ready_of(obj: dict) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), None)


def stopped(obj: dict) -> bool:
  ready = ready_of(obj) or {}
  return ready.get("status") == "False" and ready.get("reason") in FINAL


def ended(obj: dict) -> bool:
  """Ready or stopped: the provider no longer works on it, and RETENTION counts from then."""
  return (ready_of(obj) or {}).get("status") == "True" or stopped(obj)


def creation_row(obj: dict) -> dict:
  """A line of `component creation list`: what holds the name, and until when."""
  ready = ready_of(obj) or {}
  conditions = {item["type"]: item for item in (obj.get("status") or {}).get("conditions", [])}
  since = ready.get("lastTransitionTime")
  frees_at = None
  if ended(obj) and since:
    frees_at = format_time(datetime.fromisoformat(since.replace("Z", "+00:00")) + RETENTION)
  return {
    "kind": CREATION_KIND,
    "name": obj["metadata"]["name"],
    "status": creation_view(obj)["status"],
    "step": next((step for step in STEPS if (conditions.get(step) or {}).get("status") != "True"), None),
    "requestedBy": (obj["metadata"].get("annotations") or {}).get(CREATED_BY_ANNOTATION),
    "createdAt": obj["metadata"].get("creationTimestamp"),
    "freesAt": frees_at,
  }


def creation_view(obj: dict) -> dict:
  spec = obj.get("spec", {})
  status = obj.get("status") or {}
  template = spec.get("template") or {}
  ready = ready_of(obj)
  if ready is None:
    state = "pending"
  else:
    state = "ready" if ready.get("status") == "True" else ready.get("reason") or "pending"
  return {
    "kind": CREATION_KIND,
    "name": obj["metadata"]["name"],
    "system": spec.get("system"),
    "owner": spec.get("owner"),
    "template": {"name": template.get("name"), "ref": (template.get("source") or {}).get("ref"), "default": bool(template.get("default"))},
    "scmConnection": spec.get("scmConnection"),
    "visibility": spec.get("visibility"),
    "status": state,
    "repo": status.get("repo"),
    "files": status.get("files") or [],
    "appSpec": status.get("appSpec"),
    "conditions": status.get("conditions") or [],
    "createdAt": obj["metadata"].get("creationTimestamp"),
  }


def router(state, journal: Journal, teams=None) -> APIRouter:
  # /component-creations sits beside /components, not under it: a component may be named "creations".
  routes = APIRouter(prefix="/v1/catalog")

  def exists(plural: str, name: str) -> bool:
    try:
      state.get(plural, name)
      return True
    except NotFound:
      return False

  def held_by(name: str, obj: dict) -> HTTPException:
    """Why an existing creation holds the name, and the way out when it stopped."""
    if stopped(obj):
      ready = ready_of(obj)
      return HTTPException(409, (
        f"component '{name}': its last creation stopped at {ready['reason']} ({ready.get('message') or 'no message'}): "
        f"pass --replace to request it again, or free the name with: platform catalog component creation delete {name}"
      ))
    if ended(obj):
      return HTTPException(409, f"component '{name}' already created: see platform catalog component creation get {name}")
    return HTTPException(409, f"component '{name}' is still being created: follow it with platform catalog component get {name}")

  def release(obj: dict, principal: Principal) -> None:
    """Deletes an ended creation, journaled: only that exact object (uid), never one recreated meanwhile."""
    name = obj["metadata"]["name"]
    entry = journal.record("delete", CREATION_KIND, name, None, principal.actor)
    try:
      state.delete(CREATIONS, name, uid=obj["metadata"].get("uid"))
    except NotFound:
      pass
    except Conflict:
      raise HTTPException(409, f"the creation of '{name}' changed meanwhile: try again")
    journal.mark_applied(entry)

  def owner_of(request: ComponentRequest, principal: Principal) -> str:
    if request.owner is None:
      if not principal.teams:
        # Teams come from the token: one joined after it was issued only shows after a new login.
        raise HTTPException(422, f"component '{request.name}': pass --owner, the team that owns it (your token has no team; joined one just now? run 'platform login --refresh')")
      if len(principal.teams) > 1:
        raise HTTPException(422, f"component '{request.name}': pass --owner, the team that owns it (your teams: {', '.join(principal.teams)})")
      owner = principal.teams[0]
    else:
      owner = request.owner
    # The owner is a team (ADR 0026), as for every catalog entity.
    if owner not in known_teams(teams):
      raise HTTPException(422, f"component '{request.name}': team '{owner}' not found")
    return owner

  def template_of(request: ComponentRequest) -> tuple[dict, bool]:
    if request.template is not None:
      try:
        return state.get("templates", request.template), False
      except NotFound:
        raise HTTPException(422, f"component '{request.name}': template '{request.template}' not found")
    type_ = request.type or "service"
    found = [obj for obj in state.list("templates") if obj["spec"].get("type") == type_ and obj["spec"].get("default")]
    if not found:
      raise HTTPException(422, f"component '{request.name}': no default template for type '{type_}': pass --template or make one the default")
    return found[0], True

  def connection_of(request: ComponentRequest) -> dict:
    if request.scm is not None:
      try:
        connection = state.get(CONNECTIONS, request.scm)
      except NotFound:
        raise HTTPException(422, f"component '{request.name}': scm connection '{request.scm}' not found")
    else:
      connection = next((obj for obj in state.list(CONNECTIONS) if obj["spec"].get("default")), None)
      if connection is None:
        raise HTTPException(409, f"component '{request.name}': no default scm connection: pass --scm")
    current = connection_status(connection)
    if current != "ready":
      raise HTTPException(409, f"component '{request.name}': scm connection '{connection['metadata']['name']}' is not ready ({current})")
    return connection

  @routes.post("/components", status_code=202)
  def create(request: ComponentRequest, principal: Principal = Depends(current_principal)):
    # Every check runs before the CR is written: a refused request creates nothing on GitHub.
    if not exists("systems", request.system):
      raise HTTPException(422, f"component '{request.name}': system '{request.system}' not found")
    if exists(COMPONENTS, request.name):
      raise HTTPException(409, f"component '{request.name}' already exists")
    try:
      previous = state.get(CREATIONS, request.name)
    except NotFound:
      previous = None
    if previous is not None:
      if not (request.replace and stopped(previous)):
        raise held_by(request.name, previous)
      if not is_owner_or_admin(previous, principal, CREATED_BY_ANNOTATION):
        raise HTTPException(403, f"the creation of '{request.name}' can be replaced by who requested it and {ADMIN_GROUP}")
    owner = owner_of(request, principal)
    template, is_default = template_of(request)
    if request.type is not None and template["spec"].get("type") != request.type:
      raise HTTPException(422, f"component '{request.name}': template '{template['metadata']['name']}' is of type '{template['spec'].get('type')}', not '{request.type}'")
    try:
      params = coerce(template["spec"].get("parameters") or {}, request.params, template["metadata"]["name"])
    except SourceError as error:
      raise HTTPException(422, f"params.{error}")
    connection = connection_of(request)
    github = connection["spec"].get("github") or {}
    # Safe to drop: the provider never adopts a repo it did not create (nodeId), and the workdir is per uid.
    if previous is not None:
      release(previous, principal)

    spec = {
      "system": request.system,
      "owner": owner,
      "type": template["spec"].get("type"),
      "template": {
        "name": template["metadata"]["name"],
        "source": template["spec"]["source"],
        "copyWithoutRendering": template["spec"].get("copyWithoutRendering") or [],
      },
      "params": params,
      "scmConnection": connection["metadata"]["name"],
      "visibility": request.visibility or github.get("defaultVisibility") or "public",
    }
    if is_default:
      spec["template"]["default"] = True
    if request.description is not None:
      spec["description"] = request.description
    if request.prd is not None:
      spec["prd"] = request.prd
    # The PRD is the developer's text, not the platform's: only its hash reaches the journal.
    recorded = {**spec, "prd": redacted(request.prd)} if request.prd is not None else spec
    entry = journal.record("create", CREATION_KIND, request.name, recorded, principal.actor)
    body = {
      "apiVersion": f"{GROUP}/{VERSION}",
      "kind": CREATION_KIND,
      "metadata": {"name": request.name, "annotations": {CREATED_BY_ANNOTATION: principal.sub}},
      "spec": spec,
    }
    try:
      created = state.create(CREATIONS, body)
    except AlreadyExists:
      raise HTTPException(409, f"component '{request.name}' already exists")
    journal.mark_applied(entry)
    return creation_view(created)

  @routes.get("/components")
  def list_components(system: str | None = None, owner: str | None = None, principal: Principal = Depends(current_principal)):
    items = [component_view(obj) for obj in sorted(state.list(COMPONENTS), key=lambda obj: obj["metadata"]["name"])]
    return {"items": [item for item in items if (system is None or item["system"] == system) and (owner is None or item["owner"] == owner)]}

  def running_in(name: str, principal: Principal) -> list[dict]:
    """Where the component runs (ADR 0033): a read join over the Workload Instances, never stored in the
    catalog, and only in the environments the caller can use."""
    items = []
    for obj in state.list(INSTANCES):
      spec, status = obj.get("spec") or {}, obj.get("status") or {}
      if spec.get("component") != name:
        continue
      try:
        environment = state.get(ENVIRONMENTS, spec.get("environment"))
      except NotFound:
        continue
      if not can_use(environment, principal):
        continue
      items.append({
        "environment": spec["environment"], "instance": spec.get("instance"), "version": status.get("version"),
        "revision": status.get("revision"), "status": (instance_ready(obj) or {}).get("reason") or "Pending",
      })
    return sorted(items, key=lambda item: (item["environment"], item["instance"] or ""))

  @routes.get("/components/{name}")
  def get(name: str, principal: Principal = Depends(current_principal)):
    try:
      component = component_view(state.get(COMPONENTS, name))
    except NotFound:
      raise HTTPException(404, f"component '{name}' not found")
    return {**component, "runningIn": running_in(name, principal)}

  def visible_creation(name: str, principal: Principal) -> dict:
    try:
      obj = state.get(CREATIONS, name)
    except NotFound:
      raise HTTPException(404, f"no creation of component '{name}'")
    if not is_owner_or_admin(obj, principal, CREATED_BY_ANNOTATION):
      raise HTTPException(403, f"the creation of '{name}' is visible to who requested it and {ADMIN_GROUP}")
    return obj

  @routes.get("/components/{name}/creation")
  def creation(name: str, principal: Principal = Depends(current_principal)):
    return creation_view(visible_creation(name, principal))

  @routes.delete("/components/{name}/creation", status_code=204)
  def delete_creation(name: str, principal: Principal = Depends(current_principal)):
    """Frees the name of an ended creation. A running one is refused: the provider skips objects being
    deleted, so its half-made repo would be left behind."""
    obj = visible_creation(name, principal)
    if not ended(obj):
      raise HTTPException(409, f"component '{name}' is still being created: it can be deleted once it is Ready or stopped")
    release(obj, principal)

  @routes.get("/component-creations")
  def list_creations(principal: Principal = Depends(current_principal)):
    """Each person sees the creations they requested; platform-admins see all."""
    items = sorted(state.list(CREATIONS), key=lambda obj: obj["metadata"]["name"])
    return {"items": [creation_row(obj) for obj in items if is_owner_or_admin(obj, principal, CREATED_BY_ANNOTATION)]}

  return routes
