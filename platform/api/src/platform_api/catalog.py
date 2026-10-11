"""The platform catalog: Domain, System and Resource, stored as CRDs (ADR 0023).

Component and API stay in each repo's catalog-info.yaml and reach the platform by discovery (a
later slice); this module owns only the entities the platform stores itself.
"""
import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, field_validator

from .state import CATALOG_GROUP, GROUP, VERSION

# Who created the entity (token `sub`). Not the owner: the owner is a team, the creator a person.
CREATED_BY_ANNOTATION = f"{GROUP}/created-by"
LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")


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
  pass


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

  @field_validator("name", "owner", "parent", "domain", "system", "type")
  @classmethod
  def check_label(cls, value: str | None) -> str | None:
    if value is not None and not LABEL.match(value):
      raise ValueError("lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters")
    return value


def spec_from(kind: Kind, request: EntityRequest) -> dict:
  given = request.model_dump(exclude={"name"}, exclude_none=True)
  parent = [kind.parent_field] if kind.parent_field else []
  allowed = {"owner", "description", *parent, *kind.required}
  foreign = sorted(set(given) - allowed)
  if foreign:
    raise InvalidRequest(f"{', '.join(foreign)}: not a field of {kind.singular}")
  needed = [*kind.required, *(parent if kind.parent_required else [])]
  missing = [field for field in needed if field not in given]
  if missing:
    raise InvalidRequest(f"{', '.join(missing)}: required for {kind.singular}")
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
