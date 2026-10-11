"""Import of Backstage catalog files into the platform catalog (#190).

The API computes the plan from the raw Backstage documents, so the CLI, Backstage and agents get the
same plan without converting anything themselves. Applying re-computes the plan and writes only when
it matches the one the caller reviewed (planHash).
"""
from dataclasses import dataclass

from pydantic import ValidationError

from .catalog import KINDS, EntityRequest, InvalidRequest, Kind, spec_from

MAX_DOCUMENTS = 500
ACTIONS = ("create", "update", "unchanged", "skip", "forbidden", "error")
WRITES = ("create", "update")
BLOCKING = ("forbidden", "error")

PLURALS = {kind.name: plural for plural, kind in KINDS.items()}
SKIPPED = {
  "Component": "lives in the repo catalog-info.yaml",
  "API": "lives in the repo catalog-info.yaml",
  "Group": "identity lives in Keycloak (#186)",
  "User": "identity lives in Keycloak (#186)",
  "Template": "Backstage configuration, not a catalog entity",
  "Location": "Backstage configuration, not a catalog entity",
}
# Where each platform field comes from in a Backstage entity; errors name this field.
SOURCE_FIELDS = {
  "name": "metadata.name",
  "description": "metadata.description",
  "owner": "spec.owner",
  "parent": "spec.subdomainOf",
  "domain": "spec.domain",
  "system": "spec.system",
  "type": "spec.type",
}


class Invalid(Exception):
  def __init__(self, field: str, reason: str):
    super().__init__(f"{field}: {reason}")
    self.field = field
    self.reason = reason


@dataclass
class Item:
  """One document of the import and what the plan does with it. action None: still to be planned."""
  source: str
  kind: str | None
  name: str | None
  action: str | None = None
  spec: dict | None = None
  changes: dict | None = None
  field: str | None = None
  reason: str | None = None
  current: dict | None = None  # the object read from the state, for update and the hash
  applied: bool = False
  failed: str | None = None

  @property
  def plural(self) -> str | None:
    return PLURALS.get(self.kind)

  def reject(self, action: str, field: str | None, reason: str) -> None:
    self.action, self.field, self.reason, self.changes = action, field, reason, None

  def view(self) -> dict:
    result = {"kind": self.kind, "name": self.name, "action": self.action, "source": self.source}
    if self.action in WRITES:
      result["spec"] = self.spec
    for key in ("changes", "field", "reason", "failed"):
      if getattr(self, key) is not None:
        result[key] = getattr(self, key)
    if self.applied:
      result["applied"] = True
    return result


def owner_of(value):
  """group:default/team-alpha, group:team-alpha and default/team-alpha are the group team-alpha."""
  if value is None:
    return None
  if not isinstance(value, str):
    raise Invalid("spec.owner", "must be text")
  reference = value
  if ":" in reference:
    kind, reference = reference.split(":", 1)
    if kind.lower() != "group":
      raise Invalid("spec.owner", f"'{value}' is not a group: the owner of a catalog entity is a team")
  if "/" in reference:
    namespace, reference = reference.split("/", 1)
    if namespace != "default":
      raise Invalid("spec.owner", f"'{value}': namespace '{namespace}' is not supported, only 'default'")
  return reference


def convert(kind: Kind, document: dict) -> tuple[str, dict]:
  metadata, spec = document["metadata"], document["spec"]
  body = {"name": metadata["name"], "description": metadata.get("description"), "owner": owner_of(spec.get("owner"))}
  for field in (kind.parent_field, *kind.required):
    if field:
      body[field] = spec.get(SOURCE_FIELDS[field].removeprefix("spec."))
  body = {key: value for key, value in body.items() if value is not None}
  try:
    request = EntityRequest(**body)
  except ValidationError as error:
    first = error.errors()[0]
    reason = f"required for {kind.singular}" if first["type"] == "missing" else first["msg"].removeprefix("Value error, ")
    raise Invalid(SOURCE_FIELDS[first["loc"][0]], reason)
  try:
    return request.name, spec_from(kind, request)
  except InvalidRequest as error:
    # Only missing fields reach here: convert never builds a field the kind does not accept.
    field = error.fields[0]
    reason = f"required for {kind.singular}"
    if field == kind.parent_field:
      reason += f": declare the {KINDS[kind.parent_plural].singular} in the file"
    raise Invalid(SOURCE_FIELDS[field], reason)


def classify(source: str, document) -> Item:
  """Skips and conversion errors are decided here; an importable entity comes back with action None."""
  if not isinstance(document, dict) or not str(document.get("apiVersion", "")).startswith("backstage.io/"):
    return Item(source, None, None, "skip", reason="not a Backstage entity")
  kind = document.get("kind") if isinstance(document.get("kind"), str) else None
  metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
  name = metadata.get("name")
  item = Item(source, kind, None if name is None else str(name))
  namespace = metadata.get("namespace", "default")
  if item.plural is None:
    item.reject("skip", None, SKIPPED.get(kind, "not a catalog kind"))
  elif namespace != "default":
    item.reject("skip", None, f"namespace '{namespace}': the platform catalog has no namespaces")
  elif name is None:
    item.reject("error", "metadata.name", "required")
  elif not isinstance(name, str):
    item.reject("error", "metadata.name", "must be text")
  elif not isinstance(document.get("spec"), dict):
    item.reject("error", "spec", "required")
  else:
    try:
      item.name, item.spec = convert(KINDS[item.plural], document)
    except Invalid as error:
      item.reject("error", error.field, error.reason)
  return item
