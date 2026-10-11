"""The platform catalog: Domain, System and Resource, stored as CRDs (ADR 0023).

Component and API stay in each repo's catalog-info.yaml and reach the platform by discovery (a
later slice); this module owns only the entities the platform stores itself.
"""
import re
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, field_validator

from .auth import Principal, current_principal
from .environments import ADMIN_GROUP, is_owner_or_admin
from .journal import Journal
from .state import CATALOG_GROUP, GROUP, VERSION, AlreadyExists, Conflict, NotFound
from .teams import known_teams

# Who created the entity (token `sub`). Not the owner: the owner is a team, the creator a person.
CREATED_BY_ANNOTATION = f"{GROUP}/created-by"
LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
DESCRIPTION_MAX = 1000


@dataclass(frozen=True)
class Kind:
  name: str
  plural: str
  parent_field: str | None
  parent_plural: str | None
  parent_required: bool
  required: tuple[str, ...] = ()

  @property
  def singular(self) -> str:
    return self.name.lower()


# Parents first: the order of listings and of dependents.
KINDS = {
  "domains": Kind("Domain", "domains", "parent", "domains", False),
  "systems": Kind("System", "systems", "domain", "domains", True),
  "resources": Kind("Resource", "resources", "system", "systems", True, ("type",)),
}


class InvalidRequest(Exception):
  def __init__(self, message: str, fields: list[str]):
    super().__init__(message)
    # The offending fields, so the import can name them in the Backstage format.
    self.fields = fields


class EntityRequest(BaseModel):
  """One body for every kind; spec_from decides which fields the kind accepts."""
  model_config = ConfigDict(extra="forbid")

  name: str
  owner: str
  description: str | None = None
  parent: str | None = None
  domain: str | None = None
  system: str | None = None
  type: str | None = None

  @field_validator("description")
  @classmethod
  def check_description(cls, value: str | None) -> str | None:
    # One line about it; also keeps the CR far below the kube object size limit.
    if value is not None and len(value) > DESCRIPTION_MAX:
      raise ValueError(f"at most {DESCRIPTION_MAX} characters")
    return value

  @field_validator("name", "owner", "parent", "domain", "system", "type")
  @classmethod
  def check_label(cls, value: str | None) -> str | None:
    if value is not None and not LABEL.fullmatch(value):
      raise ValueError("lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters")
    return value


def spec_from(kind: Kind, request: EntityRequest) -> dict:
  given = request.model_dump(exclude={"name"}, exclude_none=True)
  parent = [kind.parent_field] if kind.parent_field else []
  allowed = {"owner", "description", *parent, *kind.required}
  foreign = sorted(set(given) - allowed)
  if foreign:
    raise InvalidRequest(f"{', '.join(foreign)}: not a field of {kind.singular}", foreign)
  needed = [*kind.required, *(parent if kind.parent_required else [])]
  missing = [field for field in needed if field not in given]
  if missing:
    raise InvalidRequest(f"{', '.join(missing)}: required for {kind.singular}", missing)
  return given


def manifest(kind: Kind, name: str, spec: dict, created_by: str) -> dict:
  return {
    "apiVersion": f"{CATALOG_GROUP}/{VERSION}",
    "kind": kind.name,
    "metadata": {"name": name, "annotations": {CREATED_BY_ANNOTATION: created_by}},
    "spec": spec,
  }


def view(kind: Kind, obj: dict) -> dict:
  """The API view: clients never couple to the CR shape."""
  spec = obj.get("spec", {})
  result = {"kind": kind.name, "name": obj["metadata"]["name"], "owner": spec.get("owner"), "description": spec.get("description")}
  if kind.parent_field:
    result[kind.parent_field] = spec.get(kind.parent_field)
  for field in kind.required:
    result[field] = spec.get(field)
  result["createdAt"] = obj["metadata"].get("creationTimestamp")
  return result


def dependents(state, kind: Kind, name: str) -> list[str]:
  """Entities whose parent reference points to kind/name, as `kind/name`, parents' kinds first."""
  found = []
  for child in KINDS.values():
    if child.parent_plural != kind.plural:
      continue
    for obj in sorted(state.list(child.plural), key=lambda item: item["metadata"]["name"]):
      if obj.get("spec", {}).get(child.parent_field) == name:
        found.append(f"{child.singular}/{obj['metadata']['name']}")
  return found


def router(state, journal: Journal, teams=None) -> APIRouter:
  routes = APIRouter(prefix="/v1/catalog")

  def kind_of(plural: str) -> Kind:
    if plural not in KINDS:
      raise HTTPException(404, f"unknown catalog kind '{plural}': use {', '.join(KINDS)}")
    return KINDS[plural]

  def fetch(kind: Kind, name: str) -> dict:
    try:
      return state.get(kind.plural, name)
    except NotFound:
      raise HTTPException(404, f"{kind.singular} '{name}' not found")

  def sorted_objects(kind: Kind) -> list[dict]:
    return sorted(state.list(kind.plural), key=lambda obj: obj["metadata"]["name"])

  def require_admin(kind: Kind, principal: Principal, verb: str) -> None:
    # Domains are the structure of the organisation: only platform admins shape it.
    if kind.plural == "domains" and ADMIN_GROUP not in principal.groups:
      raise HTTPException(403, f"{verb} a domain requires group '{ADMIN_GROUP}'")

  # Declared before /{plural}, which would otherwise take "entities" as a kind.
  @routes.get("/entities")
  def list_entities(kind: str | None = None, owner: str | None = None, principal: Principal = Depends(current_principal)):
    selected = [item for item in KINDS.values() if kind is None or item.singular == kind]
    if not selected:
      raise HTTPException(422, f"unknown kind '{kind}': use domain, system or resource")
    items = []
    for item_kind in selected:
      for obj in sorted_objects(item_kind):
        entity = view(item_kind, obj)
        if owner is None or entity["owner"] == owner:
          items.append({**entity, "parent": entity.get(item_kind.parent_field)})
    return {"items": items}

  @routes.post("/{plural}", status_code=201)
  def create(plural: str, request: EntityRequest, principal: Principal = Depends(current_principal)):
    kind = kind_of(plural)
    require_admin(kind, principal, "creating")
    try:
      spec = spec_from(kind, request)
    except InvalidRequest as error:
      raise HTTPException(422, str(error))
    # The owner is a team (ADR 0026): an entity cannot be owned by a name nobody can be a member of.
    if spec["owner"] not in known_teams(teams):
      raise HTTPException(422, f"{kind.singular} '{request.name}': team '{spec['owner']}' not found")
    parent = spec.get(kind.parent_field) if kind.parent_field else None
    if parent is not None:
      try:
        state.get(kind.parent_plural, parent)
      except NotFound:
        raise HTTPException(422, f"{kind.singular} '{request.name}': {KINDS[kind.parent_plural].singular} '{parent}' not found")
    entry = journal.record("create", kind.name, request.name, spec, principal.actor)
    try:
      created = state.create(kind.plural, manifest(kind, request.name, spec, principal.sub))
    except AlreadyExists:
      raise HTTPException(409, f"{kind.singular} '{request.name}' already exists")
    journal.mark_applied(entry)
    return view(kind, created)

  @routes.get("/{plural}")
  def list_kind(plural: str, principal: Principal = Depends(current_principal)):
    kind = kind_of(plural)
    return {"items": [view(kind, obj) for obj in sorted_objects(kind)]}

  @routes.get("/{plural}/{name}")
  def get(plural: str, name: str, principal: Principal = Depends(current_principal)):
    kind = kind_of(plural)
    return {**view(kind, fetch(kind, name)), "dependents": dependents(state, kind, name)}

  @routes.delete("/{plural}/{name}", status_code=204)
  def delete(plural: str, name: str, principal: Principal = Depends(current_principal)):
    kind = kind_of(plural)
    obj = fetch(kind, name)
    require_admin(kind, principal, "deleting")
    if kind.plural != "domains" and not is_owner_or_admin(obj, principal, CREATED_BY_ANNOTATION):
      raise HTTPException(403, f"{kind.singular} '{name}' can only be deleted by who created it or {ADMIN_GROUP}")
    # Not atomic: a child created between this check and the delete keeps a dangling reference.
    # Accepted for slice 1 (single writer, low volume); a finalizer on the parent would close it.
    found = dependents(state, kind, name)
    if found:
      raise HTTPException(409, f"{kind.singular} '{name}' has dependents: {', '.join(found)}")
    entry = journal.record("delete", kind.name, name, None, principal.actor)
    try:
      state.delete(kind.plural, name, uid=obj["metadata"].get("uid"))
    except NotFound:
      raise HTTPException(404, f"{kind.singular} '{name}' not found")
    except Conflict:
      raise HTTPException(409, f"{kind.singular} '{name}' changed while deleting: try again")
    journal.mark_applied(entry)
    return Response(status_code=204)

  return routes
