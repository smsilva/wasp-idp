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
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .auth import Principal, current_principal
from .backstage import Invalid, owner_of
from .catalog import CREATED_BY_ANNOTATION, KINDS, EntityRequest, InvalidRequest, Kind, manifest, spec_from
from .environments import ADMIN_GROUP, is_owner_or_admin
from .journal import Journal
from . import templates
from .state import AlreadyExists, Conflict, NotFound
from .teams import LABEL as TEAM_LABEL, RESERVED as TEAM_RESERVED, TeamExists, TeamsUnavailable, known_teams

MAX_DOCUMENTS = 500
ACTIONS = ("create", "update", "unchanged", "skip", "forbidden", "error")
WRITES = ("create", "update")
BLOCKING = ("forbidden", "error")

PLURALS = {kind.name: plural for plural, kind in KINDS.items()} | {templates.KIND.name: templates.KIND.plural}
ALL_KINDS = {**KINDS, templates.KIND.plural: templates.KIND}
# A Backstage Group becomes a team (ADR 0026): a Keycloak group, not a CRD, so it has no plural.
TEAM = "Group"
SKIPPED = {
  "Component": "lives in the repo catalog-info.yaml; indexed by discovery (#205)",
  "API": "lives in the repo catalog-info.yaml; indexed by discovery (#205)",
  "User": "users live in Keycloak: they sign in, never imported",
  "Location": "Backstage configuration, not a catalog entity",
  # Templates are read from scaffolder.backstage.io/* documents (classify_template).
  "Template": "a template needs apiVersion scaffolder.backstage.io/v1beta3",
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


@dataclass
class Item:
  """One document of the import and what the plan does with it. action None: still to be planned."""
  source: str
  kind: str | None
  name: str | None
  path: str | None = None  # the file, relative to the repo root: where a template's content lives
  action: str | None = None
  spec: dict | None = None
  changes: dict | None = None
  field: str | None = None
  reason: str | None = None
  current: dict | None = None  # the object read from the state, for update and the hash
  owns: list[str] | None = None  # folders of a template's content: their files are not catalog data
  applied: bool = False
  failed: str | None = None

  @property
  def plural(self) -> str | None:
    return PLURALS.get(self.kind)

  @property
  def importable(self) -> bool:
    return self.plural is not None or self.kind == TEAM

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


def classify_template(source: str, path: str, document: dict, origin: dict | None) -> list[Item]:
  """A template and one skip per scaffolder step the platform does not run."""
  backstage = "apiVersion" in document
  metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
  name = metadata.get("name") if backstage else document.get("name")
  item = Item(source, templates.KIND.name, None if name is None else str(name), path)
  # The content folders count even when the template itself has errors: its catalog-info.yaml is
  # still not a Component.
  try:
    item.owns = templates.content_folders(document, path)
  except Exception:
    item.owns = None
  try:
    convert = templates.convert_backstage if backstage else templates.convert_platform
    name, spec, steps = convert(document, path, origin)
    item.name, item.spec = templates.validate(name, spec)
  except templates.Invalid as error:
    item.reject("error", error.field, error.reason)
    return [item]
  skipped = [Item(source, "Step", f"{item.name}/{step}", path, "skip", reason=f"{action}: {reason}") for step, action, reason in steps]
  return [item, *skipped]


def classify_all(source: str, document, path: str | None = None, origin: dict | None = None) -> list[Item]:
  """One item per document, plus one per skipped step of a template."""
  path = path or source.rsplit("#", 1)[0]
  if templates.is_platform_template(path, document) or (
    isinstance(document, dict) and str(document.get("apiVersion", "")).startswith("scaffolder.backstage.io/") and document.get("kind") == "Template"
  ):
    return classify_template(source, path, document, origin)
  return [classify(source, document, path)]


def classify(source: str, document, path: str | None = None) -> Item:
  """Skips and conversion errors are decided here; an importable entity comes back with action None."""
  if not isinstance(document, dict) or not str(document.get("apiVersion", "")).startswith("backstage.io/"):
    return Item(source, None, None, path, "skip", reason="not a Backstage entity")
  kind = document.get("kind") if isinstance(document.get("kind"), str) else None
  metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
  name = metadata.get("name")
  item = Item(source, kind, None if name is None else str(name), path)
  namespace = metadata.get("namespace") or "default"
  if not item.importable or item.plural == templates.KIND.plural:
    item.reject("skip", None, SKIPPED.get(kind, "not a catalog kind"))
  elif not isinstance(namespace, str):
    item.reject("error", "metadata.namespace", "must be text")
  elif namespace != "default":
    item.reject("skip", None, f"namespace '{namespace}': the platform catalog has no namespaces")
  elif name is None:
    item.reject("error", "metadata.name", "required")
  elif not isinstance(name, str):
    item.reject("error", "metadata.name", "must be text")
  elif not isinstance(document.get("spec"), dict):
    item.reject("error", "spec", "required")
  elif item.kind == TEAM:
    # Only the name: members are e-mails (PII) and membership is `platform team member`.
    if not TEAM_LABEL.fullmatch(name):
      item.reject("error", "metadata.name", "lowercase letters, digits and '-', at most 63 characters")
    elif name in TEAM_RESERVED:
      item.reject("error", "metadata.name", f"'{name}' is reserved by the platform")
    else:
      item.spec = {}
  else:
    try:
      item.name, item.spec = convert(KINDS[item.plural], document)
    except Invalid as error:
      item.reject("error", error.field, error.reason)
  return item


# Teams first: the owner of every other entity.
KIND_ORDER = {TEAM: 0, "Domain": 1, "System": 2, "Resource": 3, "Template": 4}


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
  if kind.plural in ("domains", templates.KIND.plural) and ADMIN_GROUP not in principal.groups:
    return f"{verb} a {kind.singular} requires group '{ADMIN_GROUP}'"
  if item.action == "update" and kind.plural not in ("domains", templates.KIND.plural) and not is_owner_or_admin(item.current, principal, CREATED_BY_ANNOTATION):
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


def decide_team(item: Item, teams: set[str], principal) -> None:
  if item.name in teams:
    item.action = "unchanged"
  elif ADMIN_GROUP not in principal.groups:
    item.reject("forbidden", None, f"creating a team requires group '{ADMIN_GROUP}'")
  else:
    item.action = "create"


def decide(item: Item, declared: dict, state, principal, teams: set[str]) -> None:
  kind = ALL_KINDS[item.plural]
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
    if kind is templates.KIND:
      # Being the default is decided by `template default`, never by the files: an import keeps it,
      # unless the type changes, which would make it a second default of the new type.
      if old.get("default") and old.get("type") == item.spec.get("type"):
        item.spec = {**item.spec, "default": True}
      old, new = templates.flatten(old), templates.flatten(item.spec)
    else:
      new = item.spec
    item.changes = {
      field: [old.get(field), new.get(field)]
      for field in sorted(set(old) | set(new))
      if old.get(field) != new.get(field)
    } or None
    item.action = "update" if item.changes else "unchanged"
  if item.action in WRITES:
    # Only what the import writes: an entity saved before owners were teams stays readable.
    owner = item.spec.get("owner")
    team = declared.get((TEAM, owner))
    if owner not in teams and (team is None or team.action in BLOCKING):
      return item.reject("error", "spec.owner", f"team '{owner}' not found: declare its Group in the files or create it with 'platform team create'")
    reason = denied(kind, item, principal)
    if reason:
      item.reject("forbidden", None, reason)


def inside(path: str | None, folder: str) -> bool:
  return path is not None and (path == folder or path.startswith(folder.rstrip("/") + "/"))


def mark_template_content(items: list[Item]) -> None:
  """Files under a template's content are what the template renders, not entities: a catalog-info.yaml
  there has ${{ values.name }} as its name and is not a real Component (ADR 0024)."""
  owners = [(folder, item.name) for item in items if item.owns for folder in item.owns]
  for item in items:
    if item.kind == templates.KIND.name:
      continue
    for folder, name in owners:
      if inside(item.path, folder):
        item.reject("skip", None, f"part of template {name}")
        break


def make_plan(documents: list[dict], state, principal, teams: set[str], origin: dict | None = None, only_templates: bool = False) -> Plan:
  """teams: the names of the existing teams, read once by the caller."""
  items = [
    item
    for document in documents
    for item in classify_all(document["source"], document["document"], document.get("path"), origin)
  ]
  mark_template_content(items)
  if only_templates:
    for item in items:
      if item.action is None and item.kind != templates.KIND.name:
        item.reject("skip", None, "not a template: use 'platform catalog import'")
  # Every copy with a name counts, valid or not: an error on one copy must not hide the duplicate.
  mark_duplicates([item for item in items if item.importable and item.name and item.action != "skip"])
  domains = {item.name: item for item in items if item.kind == "Domain" and item.action is None}
  mark_cycles(domains)
  items.sort(key=lambda item: (KIND_ORDER.get(item.kind, len(KIND_ORDER)), depth(item, domains), item.name or "", item.source))
  # Skips are not entities of the import: a child pointing at one resolves against the platform.
  declared = {(item.kind, item.name): item for item in items if item.importable and item.action != "skip"}
  for item in items:
    if item.action is None and item.kind == TEAM:
      decide_team(item, teams, principal)
    elif item.action is None:
      decide(item, declared, state, principal, teams)
  return Plan(items)


FAILURES = {
  AlreadyExists: "created by someone else since the plan was made",
  Conflict: "changed since the plan was made",
  NotFound: "deleted since the plan was made",
}


def failure(error: Exception) -> str:
  """A kube ApiException's str() carries the response headers and body: keep status and reason."""
  status = getattr(error, "status", None)
  if status is not None:
    return f"kubernetes error {status}: {getattr(error, 'reason', None) or 'unknown'}"
  return str(error)


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
  # The file relative to the repo root; templates resolve their content folder from it.
  path: str | None = None
  document: Any = None


class Origin(BaseModel):
  """Where the imported files are published: templates register this repo and ref (ADR 0024)."""
  model_config = ConfigDict(extra="forbid")

  repo: str
  ref: str

  check_repo = field_validator("repo")(templates.Source.check_repo.__func__)
  check_ref = field_validator("ref")(templates.Source.check_ref.__func__)


class ImportRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  documents: list[SourceDocument] = Field(max_length=MAX_DOCUMENTS)
  dryRun: bool = True
  planHash: str | None = None
  source: Origin | None = None


def apply(plan: Plan, state, journal: Journal, principal: Principal, teams) -> None:
  """Writes in plan order and stops at the first failure. Not transactional: what was written stays,
  and importing again converges, because it shows up as unchanged."""
  for item in plan.writes:
    if item.kind == TEAM:
      entry = journal.record("create", "Team", item.name, None, principal.actor)
      try:
        teams.create(item.name)
      except (TeamExists, TeamsUnavailable) as error:
        item.failed = "created by someone else since the plan was made" if isinstance(error, TeamExists) else str(error)
        done = sum(1 for written in plan.writes if written.applied)
        raise PlanRejected(409, f"team '{item.name}': {item.failed}; {done} applied before it, import again to converge", plan.view(applied=False))
      journal.mark_applied(entry)
      item.applied = True
      continue
    kind = ALL_KINDS[item.plural]
    entry = journal.record(item.action, kind.name, item.name, item.spec, principal.actor)
    try:
      if item.action == "create":
        state.create(item.plural, manifest(kind, item.name, item.spec, principal.sub))
      else:
        # The object as read, spec replaced: created-by and resourceVersion stay.
        state.replace(item.plural, {**item.current, "spec": item.spec})
    except Exception as error:
      item.failed = FAILURES.get(type(error)) or failure(error)
      done = sum(1 for written in plan.writes if written.applied)
      raise PlanRejected(409, f"{kind.singular} '{item.name}': {item.failed}; {done} applied before it, import again to converge", plan.view(applied=False))
    journal.mark_applied(entry)
    item.applied = True


def router(state, journal: Journal, teams=None) -> APIRouter:
  routes = APIRouter(prefix="/v1/catalog")

  def run(request: ImportRequest, principal: Principal, only_templates: bool) -> dict:
    origin = request.source.model_dump() if request.source else None
    plan = make_plan([document.model_dump() for document in request.documents], state, principal, known_teams(teams), origin, only_templates)
    if request.dryRun:
      return plan.view(applied=False)
    if plan.blocked:
      raise PlanRejected(422, "the plan has entities that cannot be imported: nothing was applied", plan.view(applied=False))
    if request.planHash is not None and request.planHash != plan.hash:
      raise PlanRejected(409, "catalog changed since the plan was made: review the plan again", plan.view(applied=False))
    apply(plan, state, journal, principal, teams)
    return plan.view(applied=True)

  @routes.post("/import")
  def import_catalog(request: ImportRequest, principal: Principal = Depends(current_principal)):
    return run(request, principal, only_templates=False)

  # The same plan, limited to templates: `platform catalog template import`.
  @routes.post("/templates:import")
  def import_templates(request: ImportRequest, principal: Principal = Depends(current_principal)):
    return run(request, principal, only_templates=True)

  return routes
