"""Component templates (ADR 0024): a catalog entity pointing at content versioned in Git.

The platform keeps only the registry; the content stays in the template repo. The platform runs fixed
steps (create the repo, push, discovery), so a Backstage template's `steps` are reported, never run.
"""
import posixpath
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import Principal, current_principal
from .backstage import Invalid, owner_of
from .catalog import DESCRIPTION_MAX, LABEL, Kind, manifest
from .environments import ADMIN_GROUP
from .journal import Journal
from .state import AlreadyExists, Conflict, NotFound
from .teams import known_teams

KIND = Kind("Template", "templates", None, None, False)
TYPES = ("service", "website", "library")
# Filled by the platform on every component, never declared by a template (ADR 0024).
PLATFORM_PARAMETERS = ("name", "owner", "system", "description")
REPO_URL = re.compile(r"^https://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9._~-]+)+$")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
# Why each scaffolder action is not run: the platform owns these steps.
STEP_REASONS = {
  "publish:github": "the platform creates the repo",
  "publish:gitlab": "the platform creates the repo",
  "publish:bitbucketCloud": "the platform creates the repo",
  "publish:azure": "the platform creates the repo",
  "publish:github:pull-request": "GitOps belongs to the release",
  "catalog:register": "the platform discovery finds catalog-info.yaml",
}
DEFAULT_STEP_REASON = "the platform runs fixed steps: create the repo, push, discovery"


class Source(BaseModel):
  model_config = ConfigDict(extra="forbid")

  repo: str
  path: str
  ref: str

  @field_validator("repo")
  @classmethod
  def check_repo(cls, value: str) -> str:
    if not REPO_URL.fullmatch(value):
      raise ValueError("an https URL of a Git repository")
    return value

  @field_validator("path")
  @classmethod
  def check_path(cls, value: str) -> str:
    if value.startswith("/") or ".." in value.split("/") or not value.strip() or "\\" in value:
      raise ValueError("a folder relative to the repo root, without '..'")
    return value

  @field_validator("ref")
  @classmethod
  def check_ref(cls, value: str) -> str:
    if not REF.fullmatch(value) or ".." in value:
      raise ValueError("a tag, branch or commit")
    return value


def check_parameters(value: dict) -> dict:
  """The JSON Schema of the extra parameters: an object, without the parameters the platform fills."""
  if not value:
    return {}
  if value.get("type") != "object" or not isinstance(value.get("properties", {}), dict):
    raise ValueError("a JSON Schema of type object")
  reserved = sorted(set(value.get("properties", {})) & set(PLATFORM_PARAMETERS))
  if reserved:
    raise ValueError(f"{', '.join(reserved)}: filled by the platform, not declared by the template")
  return value


class TemplateRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  name: str
  type: Literal["service", "website", "library"]
  owner: str
  source: Source
  default: bool = False
  description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
  parameters: dict = Field(default_factory=dict)
  copyWithoutRendering: list[str] = Field(default_factory=list)

  @field_validator("name", "owner")
  @classmethod
  def check_label(cls, value: str) -> str:
    if not LABEL.fullmatch(value):
      raise ValueError("lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters")
    return value

  @field_validator("parameters")
  @classmethod
  def check_schema(cls, value: dict) -> dict:
    return check_parameters(value)

  def spec(self) -> dict:
    spec = self.model_dump(exclude={"name"}, exclude_none=True)
    # Only the default is marked; every other template has no field at all.
    if not spec["default"]:
      del spec["default"]
    return spec


def view(obj: dict) -> dict:
  spec = obj.get("spec", {})
  return {
    "kind": KIND.name,
    "name": obj["metadata"]["name"],
    "type": spec.get("type"),
    "default": bool(spec.get("default")),
    "source": spec.get("source"),
    "parameters": spec.get("parameters") or {},
    "copyWithoutRendering": spec.get("copyWithoutRendering") or [],
    "owner": spec.get("owner"),
    "description": spec.get("description"),
    "createdAt": obj["metadata"].get("creationTimestamp"),
  }


def flatten(spec: dict, prefix: str = "") -> dict:
  """source.ref instead of the whole source block, so a plan shows only what changed."""
  flat = {}
  for key, value in spec.items():
    if key == "source" and isinstance(value, dict):
      flat.update(flatten(value, f"{prefix}{key}."))
    else:
      flat[f"{prefix}{key}"] = value
  return flat


# --- conversion of documents read from files ---

def _strip_ui(schema):
  """Backstage form hints (ui:field, ui:options …) say nothing to the platform."""
  if isinstance(schema, dict):
    return {key: _strip_ui(value) for key, value in schema.items() if not str(key).startswith("ui:")}
  if isinstance(schema, list):
    return [_strip_ui(value) for value in schema]
  return schema


def merge_pages(pages) -> dict:
  """The form pages of a Backstage template become one JSON Schema of the extra parameters."""
  if isinstance(pages, dict):
    pages = [pages]
  if not isinstance(pages, list):
    raise Invalid("spec.parameters", "must be a list of form pages")
  properties, required = {}, []
  for page in pages:
    if not isinstance(page, dict):
      raise Invalid("spec.parameters", "every form page must be a mapping")
    page_properties = page.get("properties") or {}
    if not isinstance(page_properties, dict):
      raise Invalid("spec.parameters", "properties of a form page must be a mapping")
    for key, schema in page_properties.items():
      if key not in PLATFORM_PARAMETERS:
        properties[key] = _strip_ui(schema)
    required += [key for key in page.get("required") or [] if key not in PLATFORM_PARAMETERS and key not in required]
  if not properties:
    return {}
  schema = {"type": "object"}
  if required:
    schema["required"] = required
  schema["properties"] = properties
  return schema


def _relative(folder: str, url) -> str:
  """A fetch:template url, relative to the template file, as a path from the repo root."""
  if not isinstance(url, str) or "://" in url or url.startswith("/"):
    raise Invalid("spec.steps", f"fetch:template url must be a relative folder, got '{url}'")
  path = posixpath.normpath(posixpath.join(folder, url))
  if path == ".." or path.startswith("../"):
    raise Invalid("spec.steps", f"fetch:template url leaves the repo: '{url}'")
  return path


def _steps(spec: dict) -> list[dict]:
  steps = spec.get("steps") or []
  if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
    raise Invalid("spec.steps", "must be a list of mappings")
  return steps


def _type(value) -> str:
  if value not in TYPES:
    raise Invalid("spec.type", f"'{value}': use {', '.join(TYPES[:-1])} or {TYPES[-1]}")
  return value


def _source(origin: dict | None, path: str) -> dict:
  if not origin or not origin.get("repo") or not origin.get("ref"):
    raise Invalid("source.repo", "required to import templates: pass --repo and --ref")
  return {"repo": origin["repo"], "path": path, "ref": origin["ref"]}


def convert_backstage(document: dict, file: str, origin: dict | None):
  """(name, spec, skipped steps as (id, action, reason))."""
  metadata, spec = document.get("metadata") or {}, document.get("spec") or {}
  if not isinstance(metadata, dict):
    raise Invalid("metadata", "must be a mapping")
  if not isinstance(spec, dict):
    raise Invalid("spec", "must be a mapping")
  folder = posixpath.dirname(file)
  type_ = _type(spec.get("type"))
  content, steps = None, []
  for index, step in enumerate(_steps(spec), 1):
    action, inputs = step.get("action"), step.get("input") or {}
    if not isinstance(inputs, dict):
      raise Invalid("spec.steps", f"input of step {index} must be a mapping")
    identifier = step.get("id") or f"step-{index}"
    if action == "fetch:template":
      path = _relative(folder, inputs.get("url"))
      if content is None and not inputs.get("targetPath"):
        content = (path, inputs.get("copyWithoutTemplating") or inputs.get("copyWithoutRender") or [])
        continue
      steps.append((identifier, action, "renders outside the repo content (targetPath)"))
    else:
      steps.append((identifier, action, STEP_REASONS.get(action, DEFAULT_STEP_REASON)))
  if content is None:
    raise Invalid("spec.steps", "no fetch:template step: nothing to render")
  owner = owner_of(spec.get("owner"))
  if owner is None:
    raise Invalid("spec.owner", "required for template")
  result = {
    "type": type_,
    "source": _source(origin, content[0]),
    "parameters": merge_pages(spec.get("parameters") or []),
    "copyWithoutRendering": list(content[1]),
  }
  if metadata.get("description"):
    result["description"] = metadata["description"]
  result["owner"] = owner
  return metadata.get("name"), result, steps


def convert_platform(document: dict, file: str, origin: dict | None):
  """The platform format: template.yaml next to content/ (platform/templates/*)."""
  folder = posixpath.dirname(file)
  content = posixpath.join(folder, "content") if folder else "content"
  if document.get("owner") is None:
    raise Invalid("owner", "required for template")
  result = {
    "type": _type(document.get("type")),
    "source": _source(origin, content),
    "parameters": document.get("parameters") or {},
    "copyWithoutRendering": list(document.get("copyWithoutRendering") or []),
  }
  if document.get("description"):
    result["description"] = document["description"]
  result["owner"] = owner_of(document["owner"])
  return document.get("name"), result, []


def content_folders(document: dict, file: str) -> list[str]:
  """Every folder a template renders from, read leniently: used to skip their files in an import."""
  folder = posixpath.dirname(file)
  if "apiVersion" not in document:
    return [posixpath.join(folder, "content") if folder else "content"]
  spec = document.get("spec")
  steps = spec.get("steps") if isinstance(spec, dict) else None
  folders = []
  for step in steps if isinstance(steps, list) else []:
    inputs = step.get("input") if isinstance(step, dict) else None
    if step.get("action") == "fetch:template" if isinstance(step, dict) else False:
      try:
        folders.append(_relative(folder, inputs.get("url") if isinstance(inputs, dict) else None))
      except Invalid:
        pass
  return folders


def is_platform_template(file: str, document) -> bool:
  return isinstance(document, dict) and posixpath.basename(file) == "template.yaml" and "apiVersion" not in document


def validate(name, spec: dict) -> tuple[str, dict]:
  """The same rules as the create route; errors name the field of the request."""
  try:
    request = TemplateRequest(name=name, **spec)
  except Exception as error:
    first = error.errors()[0]
    field = ".".join(str(part) for part in first["loc"]) or "spec"
    raise Invalid(field, first["msg"].removeprefix("Value error, "))
  return request.name, request.spec()


# --- routes ---

def router(state, journal: Journal, teams=None) -> APIRouter:
  routes = APIRouter(prefix="/v1/catalog/templates")

  def require_admin(principal: Principal, verb: str) -> None:
    if ADMIN_GROUP not in principal.groups:
      raise HTTPException(403, f"{verb} a template requires group '{ADMIN_GROUP}'")

  def fetch(name: str) -> dict:
    try:
      return state.get(KIND.plural, name)
    except NotFound:
      raise HTTPException(404, f"template '{name}' not found")

  def exists(name: str) -> bool:
    try:
      state.get(KIND.plural, name)
      return True
    except NotFound:
      return False

  def same_type(type_: str, but: str) -> list[dict]:
    return sorted(
      (obj for obj in state.list(KIND.plural) if obj["spec"].get("type") == type_ and obj["metadata"]["name"] != but),
      key=lambda obj: obj["metadata"]["name"],
    )

  def unset_other_defaults(type_: str, but: str, principal: Principal) -> None:
    """At most one default per type: marking one unmarks the others, in the same request."""
    for obj in same_type(type_, but):
      if not obj["spec"].get("default"):
        continue
      spec = {key: value for key, value in obj["spec"].items() if key != "default"}
      entry = journal.record("update", KIND.name, obj["metadata"]["name"], spec, principal.actor)
      try:
        state.replace(KIND.plural, {**obj, "spec": spec})
      except Conflict:
        raise HTTPException(409, f"template '{obj['metadata']['name']}' changed meanwhile: run 'template default' again")
      journal.mark_applied(entry)

  @routes.post("", status_code=201)
  def create(request: TemplateRequest, principal: Principal = Depends(current_principal)):
    require_admin(principal, "creating")
    spec = request.spec()
    if exists(request.name):
      raise HTTPException(409, f"template '{request.name}' already exists")
    # The owner is a team (ADR 0026), as for every catalog entity.
    if request.owner not in known_teams(teams):
      raise HTTPException(422, f"template '{request.name}': team '{request.owner}' not found")
    # Unset first: a failure there leaves the old default in place, never two of them.
    if request.default:
      unset_other_defaults(request.type, request.name, principal)
    entry = journal.record("create", KIND.name, request.name, spec, principal.actor)
    try:
      created = state.create(KIND.plural, manifest(KIND, request.name, spec, principal.sub))
    except AlreadyExists:
      raise HTTPException(409, f"template '{request.name}' already exists")
    journal.mark_applied(entry)
    return view(created)

  @routes.get("")
  def list_templates(principal: Principal = Depends(current_principal)):
    return {"items": [view(obj) for obj in sorted(state.list(KIND.plural), key=lambda obj: obj["metadata"]["name"])]}

  @routes.get("/{name}")
  def get(name: str, principal: Principal = Depends(current_principal)):
    return view(fetch(name))

  @routes.post("/{name}/default")
  def make_default(name: str, principal: Principal = Depends(current_principal)):
    require_admin(principal, "changing the default")
    obj = fetch(name)
    if not obj["spec"].get("default"):
      spec = {**obj["spec"], "default": True}
      entry = journal.record("update", KIND.name, name, spec, principal.actor)
      try:
        obj = state.replace(KIND.plural, {**obj, "spec": spec})
      except Conflict:
        raise HTTPException(409, f"template '{name}' changed meanwhile: try again")
      journal.mark_applied(entry)
    unset_other_defaults(obj["spec"]["type"], name, principal)
    return view(obj)

  @routes.delete("/{name}", status_code=204)
  def delete(name: str, principal: Principal = Depends(current_principal)):
    require_admin(principal, "deleting")
    obj = fetch(name)
    others = same_type(obj["spec"].get("type"), name)
    if obj["spec"].get("default") and others:
      names = ", ".join(other["metadata"]["name"] for other in others)
      raise HTTPException(409, f"template '{name}' is the default for type '{obj['spec']['type']}': make another one the default first ({names})")
    entry = journal.record("delete", KIND.name, name, None, principal.actor)
    try:
      state.delete(KIND.plural, name, uid=obj["metadata"].get("uid"))
    except NotFound:
      raise HTTPException(404, f"template '{name}' not found")
    except Conflict:
      raise HTTPException(409, f"template '{name}' changed while deleting: try again")
    journal.mark_applied(entry)
    return Response(status_code=204)

  return routes
