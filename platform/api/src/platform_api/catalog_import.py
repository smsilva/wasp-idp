"""Import of Backstage catalog files into the platform catalog (#190).

The API computes the plan from the raw Backstage documents, so the CLI, Backstage and agents get the
same plan without converting anything themselves. Applying re-computes the plan and writes only when
it matches the one the caller reviewed (planHash).
"""
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .auth import Principal, current_principal
from .catalog import CREATED_BY_ANNOTATION, KINDS, EntityRequest, InvalidRequest, Kind, manifest, spec_from
from .environments import ADMIN_GROUP, is_owner_or_admin
from .journal import Journal
from .state import AlreadyExists, Conflict, NotFound

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


KIND_ORDER = {"Domain": 0, "System": 1, "Resource": 2}


@dataclass
class Plan:
  items: list[Item]

  @property
  def writes(self) -> list[Item]:
    return [item for item in self.items if item.action in WRITES]

  @property
  def blocked(self) -> bool:
    return any(item.action in BLOCKING for item in self.items)

  @property
  def hash(self) -> str:
    """What applying would write, and on top of which version: any change in between changes it."""
    payload = [
      {
        "kind": item.kind, "name": item.name, "action": item.action, "spec": item.spec,
        "resourceVersion": ((item.current or {}).get("metadata") or {}).get("resourceVersion"),
      }
      for item in self.writes
    ]
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

  def view(self, applied: bool) -> dict:
    summary = dict.fromkeys(ACTIONS, 0)
    for item in self.items:
      summary[item.action] += 1
    return {"items": [item.view() for item in self.items], "summary": summary, "planHash": self.hash, "applied": applied}


def mark_duplicates(pending: list[Item]) -> None:
  by_key = {}
  for item in pending:
    by_key.setdefault((item.kind, item.name), []).append(item)
  for (kind, name), items in by_key.items():
    if len(items) > 1:
      for item in items:
        others = ", ".join(other.source for other in items if other is not item)
        item.reject("error", "metadata.name", f"{kind.lower()} '{name}' also declared in {others}")


def mark_cycles(domains: dict[str, Item]) -> None:
  for name in domains:
    chain, current = [], name
    while current in domains and current not in chain:
      chain.append(current)
      current = domains[current].spec.get("parent")
    if current in chain:
      loop = chain[chain.index(current):] + [current]
      for member in loop[:-1]:
        if domains[member].action is None:
          domains[member].reject("error", "spec.subdomainOf", "cycle: " + " > ".join(loop))


def depth(item: Item, domains: dict[str, Item]) -> int:
  """How many importable ancestors a domain has in the import: subdomains go after their parent."""
  if item.kind != "Domain" or item.action is not None:
    return 0
  count, current = 0, item.spec.get("parent")
  while current in domains and domains[current].action is None:
    count += 1
    current = domains[current].spec.get("parent")
  return count


def exists(state, plural: str, name: str) -> bool:
  try:
    state.get(plural, name)
    return True
  except NotFound:
    return False


def denied(kind: Kind, item: Item, principal) -> str | None:
  """The same rules as the single-entity routes: domains need admin, updates need the creator."""
  verb = "creating" if item.action == "create" else "updating"
  if kind.plural == "domains" and ADMIN_GROUP not in principal.groups:
    return f"{verb} a domain requires group '{ADMIN_GROUP}'"
  if item.action == "update" and kind.plural != "domains" and not is_owner_or_admin(item.current, principal, CREATED_BY_ANNOTATION):
    return f"{kind.singular} '{item.name}' can only be updated by who created it or {ADMIN_GROUP}"
  return None


def cycle_through(item: Item, declared: dict, state) -> list[str] | None:
  """The chain back to item when its new parent descends from it, reading each ancestor from the
  import when declared there and from the platform otherwise; None when there is no such cycle."""
  chain, current = [item.name], item.spec.get("parent")
  while current is not None:
    chain.append(current)
    if current == item.name:
      return chain
    if current in chain[:-1]:
      return None  # a cycle above item that does not pass through it: reported on its own members
    in_import = declared.get(("Domain", current))
    if in_import is not None and in_import.spec is not None:
      current = in_import.spec.get("parent")
    else:
      try:
        current = (state.get("domains", current).get("spec") or {}).get("parent")
      except NotFound:
        current = None
  return None


def decide(item: Item, declared: dict, state, principal) -> None:
  kind = KINDS[item.plural]
  parent = item.spec.get(kind.parent_field) if kind.parent_field else None
  if parent is not None:
    parent_kind = KINDS[kind.parent_plural]
    in_import = declared.get((parent_kind.name, parent))
    field = SOURCE_FIELDS[kind.parent_field]
    # Items are sorted parents first, so a parent in the import is already decided.
    if in_import is not None and in_import.action in BLOCKING:
      return item.reject("error", field, f"{parent_kind.singular} '{parent}' is not importable")
    if in_import is None and not exists(state, parent_kind.plural, parent):
      return item.reject("error", field, f"{parent_kind.singular} '{parent}' not found")
    # mark_cycles sees only the import; a parent that descends from item in the platform closes a
    # cycle that no other route can create and that nothing could delete afterwards.
    loop = cycle_through(item, declared, state) if kind.plural == "domains" else None
    if loop:
      return item.reject("error", field, "cycle: " + " > ".join(loop))
  try:
    item.current = state.get(item.plural, item.name)
  except NotFound:
    item.current = None
  if item.current is None:
    item.action = "create"
  else:
    old = item.current.get("spec") or {}
    item.changes = {
      field: [old.get(field), item.spec.get(field)]
      for field in sorted(set(old) | set(item.spec))
      if old.get(field) != item.spec.get(field)
    } or None
    item.action = "update" if item.changes else "unchanged"
  if item.action in WRITES:
    reason = denied(kind, item, principal)
    if reason:
      item.reject("forbidden", None, reason)


def make_plan(documents: list[dict], state, principal) -> Plan:
  items = [classify(document["source"], document["document"]) for document in documents]
  mark_duplicates([item for item in items if item.action is None])
  domains = {item.name: item for item in items if item.kind == "Domain" and item.action is None}
  mark_cycles(domains)
  items.sort(key=lambda item: (KIND_ORDER.get(item.kind, len(KIND_ORDER)), depth(item, domains), item.name or "", item.source))
  # Skips are not entities of the import: a child pointing at one resolves against the platform.
  declared = {(item.kind, item.name): item for item in items if item.plural and item.action != "skip"}
  for item in items:
    if item.action is None:
      decide(item, declared, state, principal)
  return Plan(items)


FAILURES = {
  AlreadyExists: "created by someone else since the plan was made",
  Conflict: "changed since the plan was made",
  NotFound: "deleted since the plan was made",
}


class PlanRejected(Exception):
  """An apply that wrote nothing, or stopped midway; the error body carries the plan."""

  def __init__(self, status: int, message: str, plan: dict):
    super().__init__(message)
    self.status = status
    self.message = message
    self.plan = plan


class SourceDocument(BaseModel):
  model_config = ConfigDict(extra="forbid")

  source: str
  document: Any = None


class ImportRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  documents: list[SourceDocument] = Field(max_length=MAX_DOCUMENTS)
  dryRun: bool = True
  planHash: str | None = None


def apply(plan: Plan, state, journal: Journal, principal: Principal) -> None:
  """Writes in plan order and stops at the first failure. Not transactional: what was written stays,
  and importing again converges, because it shows up as unchanged."""
  for item in plan.writes:
    kind = KINDS[item.plural]
    entry = journal.record(item.action, kind.name, item.name, item.spec, principal.actor)
    try:
      if item.action == "create":
        state.create(item.plural, manifest(kind, item.name, item.spec, principal.sub))
      else:
        # The object as read, spec replaced: created-by and resourceVersion stay.
        state.replace(item.plural, {**item.current, "spec": item.spec})
    except Exception as error:
      item.failed = FAILURES.get(type(error), str(error))
      done = sum(1 for written in plan.writes if written.applied)
      raise PlanRejected(409, f"{kind.singular} '{item.name}': {item.failed}; {done} applied before it, import again to converge", plan.view(applied=False))
    journal.mark_applied(entry)
    item.applied = True


def router(state, journal: Journal) -> APIRouter:
  routes = APIRouter(prefix="/v1/catalog")

  @routes.post("/import")
  def import_catalog(request: ImportRequest, principal: Principal = Depends(current_principal)):
    plan = make_plan([document.model_dump() for document in request.documents], state, principal)
    if request.dryRun:
      return plan.view(applied=False)
    if plan.blocked:
      raise PlanRejected(422, "the plan has entities that cannot be imported: nothing was applied", plan.view(applied=False))
    if request.planHash is not None and request.planHash != plan.hash:
      raise PlanRejected(409, "catalog changed since the plan was made: review the plan again", plan.view(applied=False))
    apply(plan, state, journal, principal)
    return plan.view(applied=True)

  return routes
