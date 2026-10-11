# Catalog Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `platform catalog import <paths>` reads Backstage catalog files, shows a plan computed by the Platform API (create, update, unchanged, skip, forbidden, error) and applies it only after review.

**Architecture:** A new API module `platform_api/catalog_import.py` holds the conversion Backstage → platform, the plan (pure function over documents, state and principal), the apply loop and an `APIRouter` with `POST /v1/catalog/import`. Apply re-computes the plan and compares a `planHash` with the reviewed one. The state layer gains `replace` (update with `resourceVersion`). The CLI reads YAML files, calls the route twice (review, apply) and renders the plan.

**Tech Stack:** Python 3.14, FastAPI, pydantic v2, kubernetes client, Typer, httpx, PyYAML, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-10-10-catalog-import-design.md`. Issue #190, branch `feat/190-catalog-import` (already created; the spec is its first commits).

## Global Constraints

- Code style of the repo: 2-space indent, English identifiers, comments and messages; docs (`cli/docs/*.md`) in pt-BR.
- `platform/api/` and `cli/` are separate `uv` projects: run `uv run pytest` inside each. Baseline: API 85 passed, CLI 46 passed.
- Name validation uses `re.fullmatch` (already in `catalog.LABEL`); never `re.match`.
- Actions are exactly `create`, `update`, `unchanged`, `skip`, `forbidden`, `error`.
- `MAX_DOCUMENTS = 500`.
- Error envelope: `{"error": {"code", "message"}}`, plus `error.plan` when the error carries a plan.
- `dryRun` defaults to `true`.
- Skip reasons, verbatim: `not a Backstage entity`; `lives in the repo catalog-info.yaml` (Component, API); `identity lives in Keycloak (#186)` (Group, User); `Backstage configuration, not a catalog entity` (Template, Location); `not a catalog kind`; `namespace '<ns>': the platform catalog has no namespaces`.
- Messages, verbatim: `creating a domain requires group 'platform-admins'`, `updating a domain requires group 'platform-admins'`, `catalog changed since the plan was made: review the plan again`, CLI `fix the errors above; nothing was applied`, `nothing to do`, `nothing was applied`.
- Every CLI change updates `cli/docs/walkthrough.md` and `cli/docs/index.md` in the same change (#182).
- Commits end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`; messages in the repo's style (`feat(#190): ...`, pt-BR subject).

## Review Focus

- A YAML document that is not a mapping (a list, a scalar) or a Backstage entity whose `metadata.name` is a number: expected `skip`/`error` items, never a 500. Tests in Task 2.
- A YAML value PyYAML turns into a non-JSON type (an unquoted date such as `2026-10-10` in `metadata.annotations`): the CLI must still send the documents, not crash in `httpx`. Test in Task 5.
- The same file reached twice (`platform catalog import idp/catalog idp/catalog/platform.yaml`): read once, no false "also declared in" errors. Test in Task 5.
- A path that does not exist: clear error naming the path, exit 1, no API call. Test in Task 5.
- A non-admin re-importing files whose Domains already exist unchanged: `unchanged`, not `forbidden`, and the import of their own Systems goes through. Test in Task 3.

---

## File Structure

| File | Responsibility |
|---|---|
| `platform/api/src/platform_api/state.py` (modify) | `StateWriter.replace` and `KubeApplyWriter.replace` |
| `platform/api/src/platform_api/catalog.py` (modify) | `InvalidRequest.fields`, so the import names the offending field |
| `platform/api/src/platform_api/catalog_import.py` (create) | conversion, plan, hash, apply, router |
| `platform/api/src/platform_api/app.py` (modify) | mount the import router before the catalog router; `PlanRejected` handler |
| `platform/api/deploy/platform-api.yaml` (modify) | verb `update` on the catalog CRDs |
| `platform/api/tests/fakes.py` (modify) | `FakeState.replace` |
| `platform/api/tests/test_catalog_import.py` (create) | unit tests of conversion and plan |
| `platform/api/tests/test_catalog_import_api.py` (create) | route, apply, real `idp/catalog/` files |
| `platform/api/tests/test_crds.py` (modify) | RBAC grants `update` |
| `idp/catalog/platform.yaml`, `idp/app-config.yaml` (modify) | Domain `platform`; location allows `Domain` |
| `cli/src/wasp_platform/client.py` (modify) | `ApiError.plan`, `import_catalog` |
| `cli/src/wasp_platform/commands/catalog_import.py` (create) | read files, render plan, the `import` command |
| `cli/src/wasp_platform/commands/catalog.py` (modify) | register `import` |
| `cli/tests/test_catalog_import.py` (create) | CLI tests |
| `cli/docs/walkthrough.md`, `cli/docs/index.md` (modify) | docs |

---

### Task 1: Update in the state layer, field-aware validation, RBAC

**Files:**
- Modify: `platform/api/src/platform_api/state.py`
- Modify: `platform/api/src/platform_api/catalog.py` (class `InvalidRequest`, function `spec_from`)
- Modify: `platform/api/tests/fakes.py`
- Modify: `platform/api/deploy/platform-api.yaml:24-26`
- Test: `platform/api/tests/test_catalog_model.py`, `platform/api/tests/test_crds.py`

**Interfaces:**
- Produces: `StateWriter.replace(plural: str, body: dict) -> dict` — writes the whole object; raises `Conflict` when `body.metadata.resourceVersion` is stale, `NotFound` when gone. `InvalidRequest(message: str, fields: list[str])` with attribute `.fields`; `str(error)` unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `platform/api/tests/test_catalog_model.py` (check its imports first; add `from fakes import FakeState`, `from platform_api.state import Conflict, NotFound`, `from platform_api.catalog import InvalidRequest, KINDS, EntityRequest, spec_from` if missing):

```python
def test_spec_from_names_missing_fields():
  with pytest.raises(InvalidRequest) as raised:
    spec_from(KINDS["resources"], EntityRequest(name="db", owner="team-alpha"))
  assert raised.value.fields == ["type", "system"]
  assert str(raised.value) == "type, system: required for resource"


def test_fake_replace_checks_resource_version():
  state = FakeState()
  created = state.create("systems", {"metadata": {"name": "greeter"}, "spec": {"owner": "team-alpha", "domain": "messaging"}})
  replaced = state.replace("systems", {**created, "spec": {"owner": "team-beta", "domain": "messaging"}})
  assert replaced["spec"]["owner"] == "team-beta"
  assert replaced["metadata"]["uid"] == created["metadata"]["uid"]
  with pytest.raises(Conflict):
    state.replace("systems", {**created, "spec": {"owner": "team-gamma", "domain": "messaging"}})
  with pytest.raises(NotFound):
    state.replace("systems", {"metadata": {"name": "nope", "resourceVersion": "1"}, "spec": {}})
```

Append to `platform/api/tests/test_crds.py`:

```python
def test_api_role_can_update_catalog():
  deploy = Path(__file__).parents[1] / "deploy" / "platform-api.yaml"
  role = next(doc for doc in yaml.safe_load_all(deploy.read_text()) if doc and doc["kind"] == "Role")
  rule = next(rule for rule in role["rules"] if CATALOG_GROUP in rule["apiGroups"])
  assert {"create", "update", "delete"} <= set(rule["verbs"])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd platform/api && uv run pytest tests/test_catalog_model.py tests/test_crds.py -q`
Expected: 3 failures (`AttributeError: 'InvalidRequest' object has no attribute 'fields'`, `AttributeError: 'FakeState' object has no attribute 'replace'`, `assert {...} <= {...}`).

- [ ] **Step 3: Implement**

`catalog.py`, replace `class InvalidRequest` and the two `raise` lines of `spec_from`:

```python
class InvalidRequest(Exception):
  def __init__(self, message: str, fields: list[str]):
    super().__init__(message)
    # The offending fields, so the import can name them in the Backstage format.
    self.fields = fields
```

```python
  if foreign:
    raise InvalidRequest(f"{', '.join(foreign)}: not a field of {kind.singular}", foreign)
  ...
  if missing:
    raise InvalidRequest(f"{', '.join(missing)}: required for {kind.singular}", missing)
```

`state.py`: add to `StateWriter` (after `create`):

```python
  def replace(self, plural: str, body: dict) -> dict: ...
```

and to `KubeApplyWriter` (after `create`):

```python
  def replace(self, plural: str, body: dict) -> dict:
    """Writes the whole object; body.metadata.resourceVersion makes a concurrent change a 409."""
    name = body["metadata"]["name"]
    try:
      return self.api.replace_namespaced_custom_object(group_of(plural), VERSION, self.namespace, plural, name, body)
    except self._api_exception as error:
      if error.status == 409:
        raise Conflict(name) from error
      if error.status == 404:
        raise NotFound(name) from error
      raise
```

`tests/fakes.py`: add after `create`:

```python
  def replace(self, plural, body):
    store = self.stores[plural]
    name = body["metadata"]["name"]
    if name not in store:
      raise NotFound(name)
    if store[name]["metadata"]["resourceVersion"] != body["metadata"].get("resourceVersion"):
      raise Conflict(name)
    obj = _copy(body)
    self._bump(obj)
    store[name] = obj
    return _copy(obj)
```

`deploy/platform-api.yaml`, the catalog rule:

```yaml
  - apiGroups: [catalog.platform.wasp.silvios.me]
    resources: [domains, systems, resources]
    verbs: [get, list, watch, create, update, delete]
```

- [ ] **Step 4: Run the whole API suite**

Run: `cd platform/api && uv run pytest -q`
Expected: 88 passed.

- [ ] **Step 5: Commit**

```bash
git add platform/api
git commit -m "feat(#190): replace no StateWriter e verbo update no RBAC do catálogo"
```

---

### Task 2: Conversion of Backstage documents

**Files:**
- Create: `platform/api/src/platform_api/catalog_import.py`
- Test: `platform/api/tests/test_catalog_import.py`

**Interfaces:**
- Consumes: `catalog.KINDS`, `catalog.Kind`, `catalog.EntityRequest`, `catalog.spec_from`, `catalog.InvalidRequest.fields` (Task 1).
- Produces: `Item` (dataclass: `source`, `kind`, `name`, `action`, `spec`, `changes`, `field`, `reason`, `current`, `applied`, `failed`; property `plural`; methods `reject(action, field, reason)` and `view() -> dict`), `classify(source: str, document) -> Item` (action `None` means "to plan"), `owner_of(value)`, constants `PLURALS`, `SKIPPED`, `SOURCE_FIELDS`, `ACTIONS`, `WRITES`, `BLOCKING`, `MAX_DOCUMENTS`.

- [ ] **Step 1: Write the failing tests**

Create `platform/api/tests/test_catalog_import.py`:

```python
import pytest

from platform_api.catalog_import import classify, owner_of


def doc(kind, name="x", spec=None, api_version="backstage.io/v1alpha1", **metadata):
  return {"apiVersion": api_version, "kind": kind, "metadata": {"name": name, **metadata}, "spec": {} if spec is None else spec}


def test_domain_with_subdomain_owner_and_description():
  item = classify("c.yaml#2", doc("Domain", "messaging", {"owner": "group:default/team-alpha", "subdomainOf": "communication"}, description="Messages"))
  assert (item.action, item.kind, item.name, item.source) == (None, "Domain", "messaging", "c.yaml#2")
  assert item.spec == {"owner": "team-alpha", "parent": "communication", "description": "Messages"}


def test_system_and_resource_fields():
  assert classify("s", doc("System", "greeter", {"owner": "team-alpha", "domain": "messaging"})).spec == {"owner": "team-alpha", "domain": "messaging"}
  resource = classify("r", doc("Resource", "greeting-db", {"owner": "team-alpha", "system": "greeter", "type": "database"}))
  assert resource.spec == {"owner": "team-alpha", "system": "greeter", "type": "database"}


def test_backstage_only_fields_are_ignored():
  item = classify("s", doc("System", "greeter", {"owner": "team-alpha", "domain": "messaging", "lifecycle": "production", "dependsOn": ["x"]}, tags=["a"], links=[]))
  assert item.action is None
  assert item.spec == {"owner": "team-alpha", "domain": "messaging"}


@pytest.mark.parametrize("value,expected", [
  ("group:default/team-alpha", "team-alpha"),
  ("group:team-alpha", "team-alpha"),
  ("Group:default/team-alpha", "team-alpha"),
  ("default/team-alpha", "team-alpha"),
  ("team-alpha", "team-alpha"),
  (None, None),
])
def test_owner_of(value, expected):
  assert owner_of(value) == expected


@pytest.mark.parametrize("owner,reason", [
  ("user:default/silvio", "'user:default/silvio' is not a group: the owner of a catalog entity is a team"),
  ("group:acme/team-alpha", "'group:acme/team-alpha': namespace 'acme' is not supported, only 'default'"),
  (42, "must be text"),
])
def test_invalid_owner_is_error(owner, reason):
  item = classify("s", doc("System", "greeter", {"owner": owner, "domain": "messaging"}))
  assert (item.action, item.field, item.reason) == ("error", "spec.owner", reason)


@pytest.mark.parametrize("document,reason", [
  ({"site_name": "communication"}, "not a Backstage entity"),
  (["a", "b"], "not a Backstage entity"),
  ("text", "not a Backstage entity"),
  (doc("System", api_version="example.com/v1"), "not a Backstage entity"),
  (doc("Component"), "lives in the repo catalog-info.yaml"),
  (doc("API"), "lives in the repo catalog-info.yaml"),
  (doc("Group"), "identity lives in Keycloak (#186)"),
  (doc("User"), "identity lives in Keycloak (#186)"),
  (doc("Template"), "Backstage configuration, not a catalog entity"),
  (doc("Location"), "Backstage configuration, not a catalog entity"),
  (doc("Widget"), "not a catalog kind"),
  (doc("System", namespace="acme"), "namespace 'acme': the platform catalog has no namespaces"),
])
def test_skips(document, reason):
  item = classify("f.yaml#1", document)
  assert (item.action, item.reason) == ("skip", reason)


def test_skip_keeps_kind_and_name_when_present():
  item = classify("o.yaml#1", doc("Group", "team-alpha"))
  assert (item.kind, item.name) == ("Group", "team-alpha")
  assert classify("m.yml#1", {"site_name": "x"}).view() == {"kind": None, "name": None, "action": "skip", "source": "m.yml#1", "reason": "not a Backstage entity"}


@pytest.mark.parametrize("document,field,reason", [
  ({"apiVersion": "backstage.io/v1alpha1", "kind": "System", "metadata": {}, "spec": {}}, "metadata.name", "required"),
  (doc("System", 123, {"owner": "team-alpha", "domain": "d"}), "metadata.name", "must be text"),
  ({"apiVersion": "backstage.io/v1alpha1", "kind": "System", "metadata": {"name": "greeter"}}, "spec", "required"),
  (doc("System", "Greeter", {"owner": "team-alpha", "domain": "d"}), "metadata.name", "lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters"),
  (doc("System", "greeter", {"domain": "d"}), "spec.owner", "required for system"),
  (doc("System", "greeter", {"owner": "team-alpha"}), "spec.domain", "required for system: declare the domain in the file"),
  (doc("Resource", "db", {"owner": "team-alpha", "system": "greeter"}), "spec.type", "required for resource"),
  (doc("Resource", "db", {"owner": "team-alpha", "type": "database"}), "spec.system", "required for resource: declare the system in the file"),
  (doc("Domain", "d", {"owner": "team-alpha", "subdomainOf": "Bad Name"}), "spec.subdomainOf", "lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters"),
])
def test_errors_name_the_backstage_field(document, field, reason):
  item = classify("f.yaml#1", document)
  assert (item.action, item.field, item.reason) == ("error", field, reason)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd platform/api && uv run pytest tests/test_catalog_import.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'platform_api.catalog_import'`.

- [ ] **Step 3: Implement**

Create `platform/api/src/platform_api/catalog_import.py`:

```python
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
```

- [ ] **Step 4: Run them to verify they pass**

Run: `cd platform/api && uv run pytest tests/test_catalog_import.py -q`
Expected: all pass. If the `Greeter` case fails because pydantic's message differs, print `item.reason` and fix the `removeprefix`, not the test text (the text is `catalog.check_label`'s message).

- [ ] **Step 5: Commit**

```bash
git add platform/api
git commit -m "feat(#190): conversão de documentos Backstage para entidades do catálogo"
```

---

### Task 3: The plan

**Files:**
- Modify: `platform/api/src/platform_api/catalog_import.py`
- Test: `platform/api/tests/test_catalog_import.py`

**Interfaces:**
- Consumes: `Item`, `classify` (Task 2); `catalog.manifest`, `catalog.CREATED_BY_ANNOTATION`; `environments.ADMIN_GROUP`, `environments.is_owner_or_admin`; `state.NotFound`; `auth.Principal(sub, email, groups)`.
- Produces: `make_plan(documents: list[dict], state, principal) -> Plan`, where each document is `{"source": str, "document": Any}`. `Plan` (dataclass, field `items: list[Item]`) with properties `writes: list[Item]`, `blocked: bool`, `hash: str` (`"sha256:<hex>"`) and method `view(applied: bool) -> dict` (`items`, `summary` with all six actions, `planHash`, `applied`).

- [ ] **Step 1: Write the failing tests**

Append to `platform/api/tests/test_catalog_import.py` (add the imports at the top of the file):

```python
from fakes import FakeState
from platform_api.auth import Principal
from platform_api.catalog import KINDS, manifest
from platform_api.catalog_import import make_plan

ADMIN = Principal("admin-1", None, ["platform-admins"])
USER = Principal("user-1", "dev@example.com", ["platform-users"])
OTHER = Principal("user-2", "other@example.com", ["platform-users"])


def sourced(*documents):
  return [{"source": f"t.yaml#{index}", "document": document} for index, document in enumerate(documents, 1)]


def seed(state, plural, name, spec, created_by="admin-1"):
  state.create(plural, manifest(KINDS[plural], name, spec, created_by))


def actions(plan):
  return [(item.kind, item.name, item.action) for item in plan.items]


COMMUNICATION = [
  doc("Resource", "greeting-db", {"owner": "group:default/team-alpha", "system": "greeter", "type": "database"}),
  doc("System", "greeter", {"owner": "group:default/team-alpha", "domain": "messaging"}),
  doc("Domain", "messaging", {"owner": "group:default/team-alpha", "subdomainOf": "communication"}),
  doc("Domain", "communication", {"owner": "group:default/team-alpha"}),
  doc("Group", "team-alpha"),
]


def test_parents_first_regardless_of_file_order():
  plan = make_plan(sourced(*COMMUNICATION), FakeState(), ADMIN)
  assert actions(plan) == [
    ("Domain", "communication", "create"),
    ("Domain", "messaging", "create"),
    ("System", "greeter", "create"),
    ("Resource", "greeting-db", "create"),
    ("Group", "team-alpha", "skip"),
  ]
  assert plan.view(applied=False)["summary"] == {"create": 4, "update": 0, "unchanged": 0, "skip": 1, "forbidden": 0, "error": 0}


def test_unchanged_and_update_with_changes():
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-alpha"})
  seed(state, "domains", "messaging", {"owner": "team-beta", "parent": "communication", "description": "old"})
  plan = make_plan(sourced(COMMUNICATION[3], COMMUNICATION[2]), state, ADMIN)
  assert actions(plan) == [("Domain", "communication", "unchanged"), ("Domain", "messaging", "update")]
  assert plan.items[1].view()["changes"] == {"description": ["old", None], "owner": ["team-beta", "team-alpha"]}
  assert "spec" not in plan.items[0].view()


def test_update_can_move_to_another_parent():
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-alpha"})
  seed(state, "domains", "bookstore", {"owner": "team-alpha"})
  seed(state, "systems", "greeter", {"owner": "team-alpha", "domain": "communication"})
  plan = make_plan(sourced(doc("System", "greeter", {"owner": "team-alpha", "domain": "bookstore"})), state, ADMIN)
  assert plan.items[0].changes == {"domain": ["communication", "bookstore"]}


def test_parent_found_in_the_platform():
  state = FakeState()
  seed(state, "domains", "messaging", {"owner": "team-alpha"})
  plan = make_plan(sourced(COMMUNICATION[1]), state, USER)
  assert actions(plan) == [("System", "greeter", "create")]


def test_broken_reference_names_entity_and_field():
  plan = make_plan(sourced(doc("System", "orphan", {"owner": "team-alpha", "domain": "nowhere"})), FakeState(), ADMIN)
  item = plan.items[0]
  assert (item.action, item.field, item.reason) == ("error", "spec.domain", "domain 'nowhere' not found")
  assert plan.blocked


def test_children_of_an_unimportable_parent_cascade():
  documents = sourced(
    doc("Domain", "messaging", {"owner": "team-alpha", "subdomainOf": "communication"}),
    doc("System", "greeter", {"owner": "team-alpha", "domain": "messaging"}),
    doc("Domain", "communication", {}),  # no owner: error
  )
  plan = make_plan(documents, FakeState(), ADMIN)
  reasons = {item.name: (item.action, item.field, item.reason) for item in plan.items}
  assert reasons["communication"] == ("error", "spec.owner", "required for domain")
  assert reasons["messaging"] == ("error", "spec.subdomainOf", "domain 'communication' is not importable")
  assert reasons["greeter"] == ("error", "spec.domain", "domain 'messaging' is not importable")


def test_duplicates_are_errors_in_both_documents():
  plan = make_plan(sourced(COMMUNICATION[3], COMMUNICATION[3]), FakeState(), ADMIN)
  assert [(item.action, item.field, item.reason) for item in plan.items] == [
    ("error", "metadata.name", "domain 'communication' also declared in t.yaml#2"),
    ("error", "metadata.name", "domain 'communication' also declared in t.yaml#1"),
  ]


def test_same_name_in_two_kinds_is_not_a_duplicate():
  documents = sourced(doc("Domain", "platform", {"owner": "team-platform"}), doc("System", "platform", {"owner": "team-platform", "domain": "platform"}))
  assert actions(make_plan(documents, FakeState(), ADMIN)) == [("Domain", "platform", "create"), ("System", "platform", "create")]


def test_domain_cycle_is_an_error():
  documents = sourced(
    doc("Domain", "a", {"owner": "team-alpha", "subdomainOf": "b"}),
    doc("Domain", "b", {"owner": "team-alpha", "subdomainOf": "a"}),
    doc("Domain", "c", {"owner": "team-alpha", "subdomainOf": "c"}),
  )
  plan = make_plan(documents, FakeState(), ADMIN)
  assert all(item.action == "error" and item.field == "spec.subdomainOf" for item in plan.items)
  assert plan.items[0].reason.startswith("cycle: ")


def test_user_cannot_create_domain_and_children_cascade():
  plan = make_plan(sourced(*COMMUNICATION[:4]), FakeState(), USER)
  reasons = {item.name: (item.action, item.reason) for item in plan.items}
  assert reasons["communication"] == ("forbidden", "creating a domain requires group 'platform-admins'")
  assert reasons["messaging"][0] == "error"
  assert reasons["greeter"] == ("error", "domain 'messaging' is not importable")


def test_user_reimporting_unchanged_domains_imports_own_systems():
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-alpha"})
  seed(state, "domains", "messaging", {"owner": "team-alpha", "parent": "communication"})
  plan = make_plan(sourced(*COMMUNICATION[:4]), state, USER)
  assert actions(plan) == [
    ("Domain", "communication", "unchanged"),
    ("Domain", "messaging", "unchanged"),
    ("System", "greeter", "create"),
    ("Resource", "greeting-db", "create"),
  ]
  assert not plan.blocked


def test_user_cannot_update_domain():
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-beta"})
  item = make_plan(sourced(COMMUNICATION[3]), state, USER).items[0]
  assert (item.action, item.reason) == ("forbidden", "updating a domain requires group 'platform-admins'")


def test_update_of_a_system_created_by_someone_else_is_forbidden():
  state = FakeState()
  seed(state, "domains", "messaging", {"owner": "team-alpha"})
  seed(state, "systems", "greeter", {"owner": "team-beta", "domain": "messaging"}, created_by="user-1")
  document = sourced(COMMUNICATION[1])
  assert make_plan(document, state, USER).items[0].action == "update"
  assert make_plan(document, state, ADMIN).items[0].action == "update"
  item = make_plan(document, state, OTHER).items[0]
  assert (item.action, item.reason) == ("forbidden", "system 'greeter' can only be updated by who created it or platform-admins")


def test_hash_is_stable_and_follows_the_state():
  state = FakeState()
  seed(state, "domains", "communication", {"owner": "team-beta"})
  documents = sourced(*COMMUNICATION[:4])
  first = make_plan(documents, state, ADMIN).hash
  assert first.startswith("sha256:")
  assert make_plan(documents, state, ADMIN).hash == first
  seed(state, "domains", "messaging", {"owner": "team-alpha", "parent": "communication"})
  assert make_plan(documents, state, ADMIN).hash != first


def test_view_shape():
  view = make_plan(sourced(COMMUNICATION[3], doc("Group", "team-alpha")), FakeState(), ADMIN).view(applied=False)
  assert view["items"][0] == {"kind": "Domain", "name": "communication", "action": "create", "source": "t.yaml#1", "spec": {"owner": "team-alpha"}}
  assert view["applied"] is False
  assert set(view) == {"items", "summary", "planHash", "applied"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd platform/api && uv run pytest tests/test_catalog_import.py -q`
Expected: collection error, `ImportError: cannot import name 'make_plan'`.

- [ ] **Step 3: Implement**

In `catalog_import.py`, extend the imports:

```python
import hashlib
import json
from dataclasses import dataclass

from pydantic import ValidationError

from .catalog import CREATED_BY_ANNOTATION, KINDS, EntityRequest, InvalidRequest, Kind, spec_from
from .environments import ADMIN_GROUP, is_owner_or_admin
from .state import NotFound
```

Append:

```python
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
```

Note on `test_children_of_an_unimportable_parent_cascade`: `communication` is an `error` from `classify` and still sits in `declared`, so `messaging` gets "not importable"; `depth` stops at a non-pending domain, so `messaging` sorts at depth 0 and still after `communication` by name. The cascade does not depend on the order there because classify errors are final before the loop.

- [ ] **Step 4: Run them to verify they pass**

Run: `cd platform/api && uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add platform/api
git commit -m "feat(#190): plano do import — ordem, referências, diff, autorização e planHash"
```

---

### Task 4: The route, apply, and the real catalog

**Files:**
- Modify: `platform/api/src/platform_api/catalog_import.py`
- Modify: `platform/api/src/platform_api/app.py` (`_error`, handlers, `include_router`)
- Modify: `idp/catalog/platform.yaml`, `idp/app-config.yaml:223-225`
- Test: `platform/api/tests/test_catalog_import_api.py`

**Interfaces:**
- Consumes: `make_plan`, `Plan`, `Item` (Task 3); `StateWriter.replace` (Task 1); `catalog.manifest`; `Journal.record/mark_applied`.
- Produces: `POST /v1/catalog/import` with body `{"documents": [{"source", "document"}], "dryRun": bool = true, "planHash": str | null}`; `PlanRejected(status, message, plan)`; `catalog_import.router(state, journal) -> APIRouter`. Responses as in the spec, section "Códigos".

- [ ] **Step 1: Write the failing tests**

Create `platform/api/tests/test_catalog_import_api.py`:

```python
import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from fakes import FakeState
from platform_api.app import create_app
from platform_api.catalog import CREATED_BY_ANNOTATION
from platform_api.journal import Journal
from tokens import TokenFactory

CATALOG = Path(__file__).parents[3] / "idp" / "catalog"
ROUTE = "/v1/catalog/import"


@pytest.fixture
def state():
  return FakeState()


@pytest.fixture
def journal_path(tmp_path):
  return tmp_path / "journal.jsonl"


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def client(state, journal_path, tokens):
  return TestClient(create_app(state, Journal(journal_path), tokens.verifier()))


def bearer(tokens, **claims):
  return {"Authorization": f"Bearer {tokens.issue(**claims)}"}


@pytest.fixture
def admin(tokens):
  return bearer(tokens, sub="admin-1", groups=["platform-admins"])


@pytest.fixture
def user(tokens):
  return bearer(tokens)


def doc(kind, name, spec):
  return {"apiVersion": "backstage.io/v1alpha1", "kind": kind, "metadata": {"name": name}, "spec": spec}


def sourced(*documents):
  return [{"source": f"t.yaml#{index}", "document": document} for index, document in enumerate(documents, 1)]


TREE = sourced(
  doc("Domain", "communication", {"owner": "group:default/team-alpha"}),
  doc("Domain", "messaging", {"owner": "group:default/team-alpha", "subdomainOf": "communication"}),
  doc("System", "greeter", {"owner": "group:default/team-alpha", "domain": "messaging"}),
)


def journal(journal_path):
  if not journal_path.exists():
    return []
  return [json.loads(line) for line in journal_path.read_text().splitlines() if "action" in line]


def review(client, headers, documents):
  response = client.post(ROUTE, json={"documents": documents}, headers=headers)
  assert response.status_code == 200, response.text
  return response.json()


def test_dry_run_is_the_default_and_writes_nothing(client, admin, state, journal_path):
  plan = review(client, admin, TREE)
  assert [item["action"] for item in plan["items"]] == ["create"] * 3
  assert plan["applied"] is False
  assert state.list("domains") == [] and journal(journal_path) == []


def test_apply_with_the_reviewed_hash(client, admin, state, journal_path):
  plan = review(client, admin, TREE)
  response = client.post(ROUTE, json={"documents": TREE, "dryRun": False, "planHash": plan["planHash"]}, headers=admin)
  assert response.status_code == 200, response.text
  body = response.json()
  assert body["applied"] is True
  assert all(item["applied"] for item in body["items"])
  assert state.stores["systems"]["greeter"]["metadata"]["annotations"][CREATED_BY_ANNOTATION] == "admin-1"
  assert [(entry["action"], entry["kind"], entry["name"]) for entry in journal(journal_path)] == [
    ("create", "Domain", "communication"), ("create", "Domain", "messaging"), ("create", "System", "greeter"),
  ]


def test_second_import_is_all_unchanged(client, admin):
  client.post(ROUTE, json={"documents": TREE, "dryRun": False}, headers=admin)
  plan = review(client, admin, TREE)
  assert plan["summary"]["unchanged"] == 3 and plan["summary"]["create"] == 0


def test_update_keeps_creator_and_is_journaled(client, admin, user, state, journal_path):
  client.post(ROUTE, json={"documents": TREE, "dryRun": False}, headers=admin)
  changed = sourced(doc("System", "greeter", {"owner": "group:default/team-beta", "domain": "messaging"}))
  response = client.post(ROUTE, json={"documents": changed, "dryRun": False}, headers=admin)
  assert response.status_code == 200, response.text
  system = state.stores["systems"]["greeter"]
  assert system["spec"]["owner"] == "team-beta"
  assert system["metadata"]["annotations"][CREATED_BY_ANNOTATION] == "admin-1"
  assert journal(journal_path)[-1]["action"] == "update"


def test_errors_block_the_apply(client, admin, state, journal_path):
  documents = TREE + sourced(doc("System", "orphan", {"owner": "team-alpha", "domain": "nowhere"}))
  response = client.post(ROUTE, json={"documents": documents, "dryRun": False}, headers=admin)
  assert response.status_code == 422
  error = response.json()["error"]
  assert error["code"] == "invalid_request"
  assert error["plan"]["summary"]["error"] == 1
  assert state.list("domains") == [] and journal(journal_path) == []


def test_forbidden_blocks_the_apply(client, user, state):
  response = client.post(ROUTE, json={"documents": TREE, "dryRun": False}, headers=user)
  assert response.status_code == 422
  assert response.json()["error"]["plan"]["summary"]["forbidden"] == 1
  assert state.list("systems") == []


def test_stale_hash_is_409_and_writes_nothing(client, admin, state):
  plan = review(client, admin, TREE)
  client.post("/v1/catalog/domains", json={"name": "communication", "owner": "team-beta"}, headers=admin)
  response = client.post(ROUTE, json={"documents": TREE, "dryRun": False, "planHash": plan["planHash"]}, headers=admin)
  assert response.status_code == 409
  error = response.json()["error"]
  assert error["message"] == "catalog changed since the plan was made: review the plan again"
  assert error["plan"]["items"][0]["action"] == "update"
  assert state.list("systems") == []


def test_failure_midway_stops_and_reports(client, admin, state):
  def collide(obj):
    if obj["metadata"]["name"] == "communication":
      state.stores["domains"]["messaging"] = {"metadata": {"name": "messaging", "resourceVersion": "99"}, "spec": {}}
  state.on_create = collide
  response = client.post(ROUTE, json={"documents": TREE, "dryRun": False}, headers=admin)
  assert response.status_code == 409
  items = response.json()["error"]["plan"]["items"]
  assert items[0].get("applied") is True
  assert items[1]["failed"] == "created by someone else since the plan was made"
  assert "applied" not in items[2]
  assert "greeter" not in state.stores["systems"]


def test_more_than_500_documents_is_422(client, admin):
  documents = sourced(*[doc("Domain", f"d{index}", {"owner": "team-alpha"}) for index in range(501)])
  assert client.post(ROUTE, json={"documents": documents}, headers=admin).status_code == 422


def test_requires_login(client):
  assert client.post(ROUTE, json={"documents": TREE}).status_code == 401


def load_catalog():
  documents = []
  for path in sorted(CATALOG.rglob("*")):
    if path.suffix in (".yaml", ".yml"):
      loaded = [document for document in yaml.safe_load_all(path.read_text()) if document is not None]
      documents += [{"source": f"{path.relative_to(CATALOG)}#{index}", "document": document} for index, document in enumerate(loaded, 1)]
  return documents


def test_the_repo_catalog_imports_cleanly(client, admin):
  plan = review(client, admin, load_catalog())
  summary = plan["summary"]
  assert (summary["create"], summary["error"], summary["forbidden"]) == (17, 0, 0)
  assert summary["skip"] == 5  # 3 Groups of org.yaml and 2 mkdocs.yml
  created = {(item["kind"], item["name"]) for item in plan["items"] if item["action"] == "create"}
  assert {("Domain", "platform"), ("System", "platform"), ("Domain", "messaging"), ("Resource", "greeting-avatars")} <= created
  applied = client.post(ROUTE, json={"documents": load_catalog(), "dryRun": False, "planHash": plan["planHash"]}, headers=admin)
  assert applied.status_code == 200, applied.text
  assert review(client, admin, load_catalog())["summary"]["unchanged"] == 17
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd platform/api && uv run pytest tests/test_catalog_import_api.py -q`
Expected: failures with 404 (route missing) and, in the last test, `error` > 0 because `platform.yaml` has no domain yet.

- [ ] **Step 3: Implement the apply and the router**

In `catalog_import.py`, extend the imports:

```python
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .auth import Principal, current_principal
from .catalog import CREATED_BY_ANNOTATION, KINDS, EntityRequest, InvalidRequest, Kind, manifest, spec_from
from .journal import Journal
from .state import AlreadyExists, Conflict, NotFound
```

Append:

```python
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
```

- [ ] **Step 4: Wire it in `app.py`**

Change the imports and `_error`:

```python
from . import catalog, catalog_import, environments
```

```python
def _error(status: int, message, headers=None, plan: dict | None = None) -> JSONResponse:
  body = {"code": ERROR_CODES.get(status, "error"), "message": message}
  if plan is not None:
    body["plan"] = plan
  return JSONResponse({"error": body}, status, headers=headers)
```

Next to the other handlers:

```python
  @app.exception_handler(catalog_import.PlanRejected)
  def plan_rejected(request: Request, error: catalog_import.PlanRejected):
    return _error(error.status, error.message, plan=error.plan)
```

Replace `app.include_router(catalog.router(state, journal))` with:

```python
  # Before the catalog router: its POST /{plural} would otherwise take "import" as a kind.
  app.include_router(catalog_import.router(state, journal))
  app.include_router(catalog.router(state, journal))
```

- [ ] **Step 5: Give the System `platform` a domain**

In `idp/catalog/platform.yaml`, insert a Domain document before the System and add `domain: platform` to the System:

```yaml
---
# The platform team's own area: the shared infrastructure every product deploys to.
# https://backstage.io/docs/features/software-catalog/descriptor-format#kind-domain
apiVersion: backstage.io/v1alpha1
kind: Domain
metadata:
  name: platform
  description: The platform team's own area — shared infrastructure for every product
spec:
  owner: group:default/team-platform
---
# Shared platform infrastructure. The k3d environment clusters are not part of any
# product System: every Component created by the python-service template depends on
# them (#118).
# https://backstage.io/docs/features/software-catalog/descriptor-format#kind-system
apiVersion: backstage.io/v1alpha1
kind: System
metadata:
  name: platform
  description: Shared platform infrastructure — the environment clusters every app deploys to
spec:
  owner: group:default/team-platform
  domain: platform
```

(the two Resource documents stay as they are). In `idp/app-config.yaml`, the location of `../../catalog/platform.yaml`:

```yaml
      rules:
        - allow: [Domain, System, Resource]
```

- [ ] **Step 6: Run the whole API suite**

Run: `cd platform/api && uv run pytest -q`
Expected: all pass. In `test_the_repo_catalog_imports_cleanly`, if the counts differ, print `plan["items"]` and check the YAML of `idp/catalog/`, not the expected numbers: 5 Domains + 4 Systems + 8 Resources = 17.

- [ ] **Step 7: Commit**

```bash
git add platform/api idp/catalog/platform.yaml idp/app-config.yaml
git commit -m "feat(#190): POST /v1/catalog/import com dryRun, planHash e aplicação na ordem"
```

---

### Task 5: The CLI command

**Files:**
- Modify: `cli/src/wasp_platform/client.py`
- Create: `cli/src/wasp_platform/commands/catalog_import.py`
- Modify: `cli/src/wasp_platform/commands/catalog.py` (end of file)
- Test: `cli/tests/test_catalog_import.py`

**Interfaces:**
- Consumes: `POST /v1/catalog/import` (Task 4); `output.print_table`, `print_json`, `success`, `fail`, `Format`, `OutputOption`.
- Produces: `ApiError(message, plan: dict | None = None)` with `.plan`; `PlatformClient.import_catalog(documents: list[dict], dry_run: bool, plan_hash: str | None = None) -> dict`; `read_documents(paths: list[Path]) -> list[dict]`; `ImportFileError`; the command `platform catalog import`.

- [ ] **Step 1: Write the failing tests**

Create `cli/tests/test_catalog_import.py`:

```python
import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app
from wasp_platform.commands.catalog_import import ImportFileError, read_documents

runner = CliRunner()
ACTIONS = ("create", "update", "unchanged", "skip", "forbidden", "error")
CREATE = {"kind": "Domain", "name": "messaging", "action": "create", "source": "c.yaml#2", "spec": {"owner": "team-alpha", "parent": "communication"}}
UPDATE = {"kind": "Resource", "name": "greeting-db", "action": "update", "source": "c.yaml#3", "spec": {}, "changes": {"owner": ["team-beta", "team-alpha"], "description": ["old", None]}}
SKIP = {"kind": "Group", "name": "team-alpha", "action": "skip", "source": "o.yaml#1", "reason": "identity lives in Keycloak (#186)"}
ERROR = {"kind": "System", "name": "orphan", "action": "error", "source": "x.yaml#1", "field": "spec.domain", "reason": "domain 'nowhere' not found"}
UNCHANGED = {"kind": "Domain", "name": "communication", "action": "unchanged", "source": "c.yaml#1"}


def plan(*items, applied=False):
  summary = dict.fromkeys(ACTIONS, 0)
  for item in items:
    summary[item["action"]] += 1
  return {"items": list(items), "summary": summary, "planHash": "sha256:abc", "applied": applied}


@pytest.fixture
def api(monkeypatch):
  calls = []
  responses = {"review": (200, plan(CREATE, UPDATE, SKIP)), "apply": (200, plan({**CREATE, "applied": True}, {**UPDATE, "applied": True}, SKIP, applied=True))}

  def handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/v1/catalog/import"
    body = json.loads(request.content)
    calls.append(body)
    status, payload = responses["review" if body["dryRun"] else "apply"]
    return httpx.Response(status, json=payload)

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  api.calls, api.responses = calls, responses
  return api


@pytest.fixture
def files(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  (tmp_path / "catalog" / "team").mkdir(parents=True)
  (tmp_path / "catalog" / "b.yaml").write_text("kind: Domain\nmetadata:\n  name: b\n---\n---\nkind: System\nmetadata:\n  name: s\n")
  (tmp_path / "catalog" / "team" / "a.yml").write_text("kind: Group\nmetadata:\n  name: team-alpha\n")
  (tmp_path / "catalog" / "notes.txt").write_text("ignored")
  return tmp_path


def run(*args, input=None):
  return runner.invoke(app, ["catalog", "import", *args], input=input)


def test_read_folder_recursive_sorted_and_multi_document(files):
  documents = read_documents([files / "catalog"])
  assert [document["source"] for document in documents] == ["catalog/b.yaml#1", "catalog/b.yaml#2", "catalog/team/a.yml#1"]
  assert documents[1]["document"]["kind"] == "System"


def test_same_file_twice_is_read_once(files):
  documents = read_documents([files / "catalog", files / "catalog" / "b.yaml"])
  assert len(documents) == 3


def test_dates_become_text(files):
  (files / "dated.yaml").write_text("kind: Domain\nmetadata:\n  name: d\n  annotations:\n    since: 2026-10-10\n")
  document = read_documents([files / "dated.yaml"])[0]["document"]
  assert document["metadata"]["annotations"]["since"] == "2026-10-10"
  json.dumps(document)


def test_missing_path_and_invalid_yaml(files):
  with pytest.raises(ImportFileError, match="nope.yaml: no such file or directory"):
    read_documents([files / "nope.yaml"])
  (files / "bad.yaml").write_text("kind: [unclosed\n")
  with pytest.raises(ImportFileError, match=r"bad.yaml:\d+: invalid YAML"):
    read_documents([files / "bad.yaml"])
  (files / "empty").mkdir()
  with pytest.raises(ImportFileError, match="no YAML documents found"):
    read_documents([files / "empty"])


def test_missing_path_fails_without_calling_the_api(api, files):
  result = run("nope.yaml")
  assert result.exit_code == 1
  assert "nope.yaml: no such file or directory" in result.output
  assert api.calls == []


def test_review_table(api, files):
  result = run("catalog", "--dry-run")
  assert result.exit_code == 0, result.output
  lines = result.output.splitlines()
  assert lines[0].split() == ["KIND", "NAME", "ACTION", "DETAIL"]
  assert "parent communication" in lines[1]
  assert "description: old → —; owner: team-beta → team-alpha" in lines[2]
  assert "identity lives in Keycloak (#186)" in lines[3]
  assert "1 to create, 1 to update, 0 unchanged, 1 skipped." in result.output
  assert [call["dryRun"] for call in api.calls] == [True]


def test_confirm_sends_the_reviewed_hash(api, files):
  result = run("catalog", input="y\n")
  assert result.exit_code == 0, result.output
  assert "Apply? [y/N]" in result.output
  assert "✓ 1 created, 1 updated" in result.output
  assert api.calls[1] == {"documents": api.calls[0]["documents"], "dryRun": False, "planHash": "sha256:abc"}


def test_refuse_applies_nothing(api, files):
  result = run("catalog", input="n\n")
  assert result.exit_code == 0
  assert "nothing was applied" in result.output
  assert len(api.calls) == 1


def test_yes_applies_without_hash(api, files):
  result = run("catalog", "--yes")
  assert result.exit_code == 0, result.output
  assert "Apply?" not in result.output
  assert api.calls[1]["planHash"] is None


def test_errors_stop_before_asking(api, files):
  api.responses["review"] = (200, plan(CREATE, ERROR))
  result = run("catalog", "--yes")
  assert result.exit_code == 1
  assert "spec.domain: domain 'nowhere' not found (x.yaml#1)" in result.output
  assert "fix the errors above; nothing was applied" in result.output
  assert len(api.calls) == 1


def test_nothing_to_do(api, files):
  api.responses["review"] = (200, plan(UNCHANGED, SKIP))
  result = run("catalog")
  assert result.exit_code == 0
  assert "nothing to do" in result.output
  assert len(api.calls) == 1


def test_json_without_yes_is_a_dry_run(api, files):
  result = run("catalog", "--output", "json")
  assert result.exit_code == 0
  assert json.loads(result.output)["planHash"] == "sha256:abc"
  assert len(api.calls) == 1


def test_json_with_yes_prints_the_result(api, files):
  result = run("catalog", "--output", "json", "--yes")
  assert result.exit_code == 0
  assert json.loads(result.output)["applied"] is True


def test_stale_plan_shows_the_new_plan(api, files):
  message = "catalog changed since the plan was made: review the plan again"
  api.responses["apply"] = (409, {"error": {"code": "conflict", "message": message, "plan": plan({**UPDATE, "changes": {"owner": ["team-gamma", "team-alpha"]}})}})
  result = run("catalog", input="y\n")
  assert result.exit_code == 1
  assert "owner: team-gamma → team-alpha" in result.output
  assert f"409: {message}" in result.output
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd cli && uv run pytest tests/test_catalog_import.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'wasp_platform.commands.catalog_import'`.

- [ ] **Step 3: Implement the client**

In `cli/src/wasp_platform/client.py`, replace `class ApiError` and the error raise in `_request`, and add the method after `list_catalog_entities`:

```python
class ApiError(Exception):
  def __init__(self, message: str, plan: dict | None = None):
    super().__init__(message)
    # The catalog import answers 409/422 with the plan, so the CLI can show what happened.
    self.plan = plan
```

```python
    if response.is_error:
      raise ApiError(_detail(response), plan=_plan(response))
```

```python
  def import_catalog(self, documents: list[dict], dry_run: bool, plan_hash: str | None = None) -> dict:
    return self._request("POST", "/v1/catalog/import", json={"documents": documents, "dryRun": dry_run, "planHash": plan_hash})
```

and after `_detail`:

```python
def _plan(response: httpx.Response) -> dict | None:
  try:
    return (response.json().get("error") or {}).get("plan")
  except (ValueError, AttributeError):
    return None
```

- [ ] **Step 4: Implement the command**

Create `cli/src/wasp_platform/commands/catalog_import.py`:

```python
"""platform catalog import: Backstage catalog files into the platform catalog (#190).

The API computes the plan; this module only reads the files, shows the plan and asks.
"""
import json
import os
from pathlib import Path
from typing import Annotated

import typer
import yaml

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, print_table, success

PARENT_FIELDS = {"Domain": "parent", "System": "domain", "Resource": "system"}
SUFFIXES = (".yaml", ".yml")


class ImportFileError(Exception):
  pass


def _files(paths: list[Path]) -> list[Path]:
  found = []
  for path in paths:
    if path.is_dir():
      found += sorted(file for file in path.rglob("*") if file.is_file() and file.suffix in SUFFIXES)
    elif path.is_file():
      found.append(path)
    else:
      raise ImportFileError(f"{path}: no such file or directory")
  unique = {}
  for file in found:
    unique.setdefault(file.resolve(), file)
  return list(unique.values())


def read_documents(paths: list[Path]) -> list[dict]:
  """Every non-empty YAML document, with its source as `<path relative to cwd>#<position>`."""
  documents = []
  for file in _files(paths):
    shown = os.path.relpath(file)
    try:
      loaded = [document for document in yaml.safe_load_all(file.read_text()) if document is not None]
    except yaml.YAMLError as error:
      mark = getattr(error, "problem_mark", None)
      line = f":{mark.line + 1}" if mark else ""
      raise ImportFileError(f"{shown}{line}: invalid YAML: {getattr(error, 'problem', None) or error}")
    for index, document in enumerate(loaded, 1):
      # Dates and other YAML-only types travel as text.
      documents.append({"source": f"{shown}#{index}", "document": json.loads(json.dumps(document, default=str))})
  if not documents:
    raise ImportFileError(f"no YAML documents found in {', '.join(str(path) for path in paths)}")
  return documents


def _value(value) -> str:
  return "—" if value is None else str(value)


def _detail(item: dict) -> str:
  action = item["action"]
  if item.get("failed"):
    return f"failed: {item['failed']}"
  if action == "create":
    field = PARENT_FIELDS.get(item["kind"])
    parent = (item.get("spec") or {}).get(field)
    return f"{field} {parent}" if parent else ""
  if action == "update":
    return "; ".join(f"{field}: {_value(old)} → {_value(new)}" for field, (old, new) in sorted(item["changes"].items()))
  if action == "skip":
    return item["reason"]
  if action == "forbidden":
    return f"{item['reason']} ({item['source']})"
  if action == "error":
    return f"{item['field']}: {item['reason']} ({item['source']})"
  return ""


def _action(item: dict) -> str:
  return item["action"] + (" ✓" if item.get("applied") else "") + (" ✗" if item.get("failed") else "")


def _print_plan(plan: dict) -> None:
  print_table(
    ["KIND", "NAME", "ACTION", "DETAIL"],
    [[_value(item["kind"]), _value(item["name"]), _action(item), _detail(item)] for item in plan["items"]],
  )
  summary = plan["summary"]
  parts = [f"{summary['create']} to create", f"{summary['update']} to update", f"{summary['unchanged']} unchanged", f"{summary['skip']} skipped"]
  if summary["forbidden"]:
    parts.append(f"{summary['forbidden']} forbidden")
  if summary["error"]:
    parts.append(f"{summary['error']} error" + ("s" if summary["error"] > 1 else ""))
  typer.echo("")
  typer.echo(", ".join(parts) + ".")


def _show(plan: dict, output: Format) -> None:
  print_json(plan) if output == Format.json else _print_plan(plan)


def import_catalog(
  paths: Annotated[list[Path], typer.Argument(help="Backstage catalog files or folders (recursive: *.yaml, *.yml).")],
  dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the plan and exit.")] = False,
  yes: Annotated[bool, typer.Option("--yes", help="Apply without asking.")] = False,
  output: OutputOption = Format.table,
):
  """Import Domains, Systems and Resources from Backstage catalog files, after reviewing the plan."""
  try:
    documents = read_documents(paths)
    client = PlatformClient()
    plan = client.import_catalog(documents, dry_run=True)
  except (ImportFileError, ApiError) as error:
    fail(str(error))
  summary = plan["summary"]
  blocked = summary["error"] + summary["forbidden"] > 0
  pending = summary["create"] + summary["update"] > 0
  # JSON is for machines: it never asks, so without --yes it is a dry run.
  if output == Format.json and (blocked or not pending or dry_run or not yes):
    print_json(plan)
    raise typer.Exit(1 if blocked else 0)
  if output == Format.table:
    _print_plan(plan)
    if blocked:
      fail("fix the errors above; nothing was applied")
    if not pending:
      typer.echo("nothing to do")
      return
    if dry_run:
      return
    if not yes and not typer.confirm("Apply?", default=False):
      typer.echo("nothing was applied")
      return
  try:
    result = client.import_catalog(documents, dry_run=False, plan_hash=None if yes else plan["planHash"])
  except ApiError as error:
    if error.plan:
      _show(error.plan, output)
    fail(str(error))
  if output == Format.json:
    print_json(result)
    return
  written = [item for item in result["items"] if item.get("applied")]
  created = sum(1 for item in written if item["action"] == "create")
  success(f"{created} created, {len(written) - created} updated")
```

In `cli/src/wasp_platform/commands/catalog.py`, next to the other imports:

```python
from .catalog_import import import_catalog
```

and at the end of the file, after the three `app.add_typer` lines:

```python
app.command("import")(import_catalog)
```

- [ ] **Step 5: Run the whole CLI suite**

Run: `cd cli && uv run pytest -q`
Expected: all pass. If `typer.confirm`'s prompt text differs from `Apply? [y/N]`, print `result.output` and match the actual Typer 0.27 prompt in the test, keeping `default=False`.

- [ ] **Step 6: Commit**

```bash
git add cli
git commit -m "feat(#190): platform catalog import na CLI"
```

---

### Task 6: Docs

**Files:**
- Modify: `cli/docs/walkthrough.md` (new step after `## 13. Catálogo`; renumber `## 14. Limpar e sair` to `## 15.`)
- Modify: `cli/docs/index.md` (section `## 11. Catálogo`, table `## Referência rápida`)

- [ ] **Step 1: Walkthrough**

Insert before `## 14. Limpar e sair`, and rename that heading to `## 15. Limpar e sair`:

````markdown
## 14. Importar o catálogo do Backstage

O `idp/catalog/` é a carga inicial do catálogo (ADR 0023). O import mostra o plano e só grava depois da confirmação.

```bash
platform catalog import idp/catalog/
```

```
KIND      NAME                  ACTION  DETAIL
Domain    bookstore             create
Domain    communication         create
Domain    platform              create
Domain    messaging             create  parent communication
Domain    notifications         create  parent communication
System    bookinfo              create  domain bookstore
System    greeter               create  domain messaging
System    notifier              create  domain notifications
System    platform              create  domain platform
Resource  development           create  system platform
...
—         —                     skip    not a Backstage entity
Group     team-alpha            skip    identity lives in Keycloak (#186)

17 to create, 0 to update, 0 unchanged, 5 skipped.
Apply? [y/N]: y
✓ 17 created, 0 updated
```

Rodar de novo não grava nada:

```bash
platform catalog import idp/catalog/
```

```
...
0 to create, 0 to update, 17 unchanged, 5 skipped.
nothing to do
```
````

Replace the `...` lines with the real output captured in Task 7.

- [ ] **Step 2: Guide**

In `cli/docs/index.md`, at the end of `## 11. Catálogo` (before `## 12. Desmontar tudo`):

````markdown
### Importar do Backstage

Quem já tem um catálogo no formato Backstage importa os arquivos de uma vez. A Platform API calcula o plano; nada é gravado antes da confirmação.

```bash
platform catalog import idp/catalog/            # arquivo ou pasta (recursivo: *.yaml, *.yml)
platform catalog import idp/catalog/ --dry-run  # só o plano
platform catalog import idp/catalog/ --yes      # sem perguntar (pipeline)
```

| Ação | Significado |
|---|---|
| `create` | não existe na plataforma |
| `update` | existe e muda; o detalhe mostra `campo: antes → depois` |
| `unchanged` | existe igual |
| `skip` | não é importado: Component e API moram no repo, Group e User no Keycloak |
| `forbidden` | sem permissão: domínio só `platform-admins`; sistema e recurso só quem criou |
| `error` | campo faltando ou referência quebrada; o detalhe diz o campo e o arquivo |

Com `forbidden` ou `error` nada é aplicado. O import nunca apaga: o que existe na plataforma e não está nos arquivos fica como está. Um campo ausente no arquivo (a `description`, por exemplo) é removido da entidade. Se o catálogo mudar entre o plano e a confirmação, a API recusa e a CLI mostra o plano novo.
````

In `## Referência rápida`, after the `platform catalog <kind> list|get|delete` row:

```markdown
| `platform catalog import <caminho>... [--dry-run] [--yes]` | importa Domain, System e Resource de arquivos Backstage, depois de revisar o plano |
```

- [ ] **Step 3: Commit**

```bash
git add cli/docs
git commit -m "docs(#190): import do catálogo no guia e no walkthrough da CLI"
```

---

### Task 7: Acceptance in the local cluster

Needs the human partner for the login (device code, personal Google account in `platform-admins`).

- [ ] **Step 1: Deploy the new API**

```bash
source ~/.credentials/bash_gcp_idp
cd cli && uv run platform init --target local
```

Expected: the Platform API image is rebuilt and rolled out; `kubectl --context k3d-platform-local --namespace platform-system get role platform-api -o yaml | grep update` shows `update` in the catalog rule.

- [ ] **Step 2: Login**

```bash
cd cli && uv run platform login --use-device-code
uv run platform whoami
```

Pass the URL and code to the human partner; expected `platform-admins` in the groups.

- [ ] **Step 3: Import, review, confirm**

```bash
cd /home/silvios/git/wasp-idp && uv run --project cli platform catalog import idp/catalog/
```

Expected: 17 `create` (5 Domains, 4 Systems, 8 Resources), 5 `skip`; answer `y`; `✓ 17 created, 0 updated`. Then `uv run --project cli platform catalog list` shows the 17.

- [ ] **Step 4: Re-run and a broken reference**

```bash
uv run --project cli platform catalog import idp/catalog/
printf 'apiVersion: backstage.io/v1alpha1\nkind: System\nmetadata:\n  name: orphan\nspec:\n  owner: team-alpha\n  domain: nowhere\n' > /tmp/orphan.yaml
uv run --project cli platform catalog import /tmp/orphan.yaml; echo "exit=$?"
```

Expected: first `17 unchanged` and `nothing to do`; then `spec.domain: domain 'nowhere' not found (../../../tmp/orphan.yaml#1)` or similar, `fix the errors above; nothing was applied`, `exit=1`.

- [ ] **Step 5: Fill the walkthrough with the real output and commit**

Replace the `...` in `cli/docs/walkthrough.md` step 14 with the captured output.

```bash
git add cli/docs/walkthrough.md
git commit -m "docs(#190): saída real do import no walkthrough"
```
