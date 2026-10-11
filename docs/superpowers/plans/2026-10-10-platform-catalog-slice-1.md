# Platform Catalog — Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Domain (with subdomains), System and Resource stored by the platform as CRDs, created, listed, read and deleted through the Platform API and the `platform catalog` CLI.

**Architecture:** Three namespaced CRDs in the new group `catalog.platform.wasp.silvios.me`. The Platform API gets a `catalog` module that holds the kind table, the pure rules (fields per kind, references, dependents) and an `APIRouter` with the routes. The router is mounted in `create_app` next to the environment routes. The CLI gets a `catalog` command group with one sub-group per kind and talks only to the API.

**Tech Stack:** Python 3.14, FastAPI, pydantic v2, kubernetes client, Typer, httpx, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-10-10-platform-catalog-design.md`. Issue #191, branch `feat/191-catalog-domain-system-resource` (already created; the spec is its first commit).

## Global Constraints

- Python code uses **2-space indentation**, as in the rest of `platform/api` and `cli`.
- Code, comments, CLI help and error messages in English. Docs (`README.md`, `cli/docs/*.md`, ADR body) in pt-BR, with the H1 title of a new doc in English.
- Run tests inside each project: `cd platform/api && uv run pytest -q` and `cd cli && uv run pytest -q`. Never `pip install`.
- CRD group `catalog.platform.wasp.silvios.me`, version `v1alpha1`, namespace `platform-system`, plurals `domains`, `systems`, `resources`.
- Name, `owner`, parent references and `type`: DNS-1123 label, regex `^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$`.
- `Domain.parent` is optional. `System.domain`, `Resource.system` and `Resource.type` are required. `owner` is required on all three. `description` is optional on all three.
- Creator annotation `platform.wasp.silvios.me/created-by` = token `sub`. It is not the owner.
- Domain create and delete: `platform-admins` only. System and Resource: any authenticated user creates; only the creator or `platform-admins` deletes.
- Every error keeps the API shape `{"error": {"code", "message"}}` (already handled by `create_app`).
- Create returns `201`, delete returns `204`.
- Commits: Conventional Commits in pt-BR (`feat(#191): …`), ending with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Never commit on `main`.
- Every CLI command change also updates `cli/docs/walkthrough.md` in the same change (#182).

## Review Focus

- **Same name in two kinds** (domain `greeter` and system `greeter`): both must be created. The test fake used to index only by name. Pinned in Task 1 (`test_stores_are_per_plural`) and Task 3 (`test_same_name_in_two_kinds`).
- **A field that belongs to another kind** (`type` on a domain, `parent` on a system): `422` naming the field, not a silent drop. Pinned in Task 2 (`test_spec_rejects_field_of_other_kind`).
- **Deleting a parent whose only children are subdomains**: `409`. Deleting the leaf subdomain and then the parent works. Pinned in Task 3 (`test_delete_leaf_then_parent`).
- **`GET /v1/catalog/entities` shadowed by `/{plural}`**: the aggregated route must answer, not `404 unknown kind 'entities'`. Pinned in Task 3 (`test_entities_filters`), and the route is declared first.
- **`204` with an empty body on delete**: the CLI client must not crash parsing JSON. Pinned in Task 4 (`test_delete_prints_success`).

---

### Task 1: Storage per plural: CRDs, RBAC, group per plural and a per-plural test fake

**Files:**
- Create: `platform/crds/catalog-domain.yaml`, `platform/crds/catalog-system.yaml`, `platform/crds/catalog-resource.yaml`
- Create: `platform/api/tests/fakes.py`
- Create: `platform/api/tests/test_crds.py`
- Modify: `platform/api/src/platform_api/state.py` (constants and every `GROUP` use inside `KubeApplyWriter`)
- Modify: `platform/api/deploy/platform-api.yaml` (Role rules)
- Modify: `platform/api/tests/test_api.py` (remove the `FakeState` class, import it from `fakes`)
- Modify: `platform/api/tests/test_auth.py:11` (import from `fakes`)

**Interfaces:**
- Produces: `state.CATALOG_GROUP = "catalog.platform.wasp.silvios.me"`, `state.CATALOG_PLURALS = ("domains", "systems", "resources")`, `state.group_of(plural: str) -> str`.
- Produces: `fakes.FakeState` with `stores: dict[str, dict[str, dict]]`, the property `objects` (the `environments` store), `create(plural, body)`, `replace_status(plural, body)`, `delete(plural, name, uid=None)`, `get(plural, name)`, `list(plural)`, and the hooks `on_create` and `before_delete`.

- [ ] **Step 1: Write the failing tests**

`platform/api/tests/test_crds.py`:

```python
"""The CRDs and the API agree on group, kinds and required fields."""
from pathlib import Path

import pytest
import yaml

from fakes import FakeState
from platform_api.state import CATALOG_GROUP, CATALOG_PLURALS, GROUP, group_of

CRDS = Path(__file__).parents[3] / "platform" / "crds"


def load(plural: str) -> dict:
  return yaml.safe_load((CRDS / f"catalog-{plural.removesuffix('s')}.yaml").read_text())


@pytest.mark.parametrize("plural,required", [
  ("domains", ["owner"]),
  ("systems", ["owner", "domain"]),
  ("resources", ["owner", "type", "system"]),
])
def test_catalog_crd(plural, required):
  crd = load(plural)
  assert crd["metadata"]["name"] == f"{plural}.{CATALOG_GROUP}"
  assert crd["spec"]["group"] == CATALOG_GROUP
  assert crd["spec"]["names"]["plural"] == plural
  spec = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["spec"]
  assert sorted(spec["required"]) == sorted(required)


def test_group_of():
  assert group_of("environments") == GROUP
  assert all(group_of(plural) == CATALOG_GROUP for plural in CATALOG_PLURALS)


def test_stores_are_per_plural():
  state = FakeState()
  state.create("domains", {"metadata": {"name": "greeter"}, "spec": {}})
  state.create("systems", {"metadata": {"name": "greeter"}, "spec": {}})
  assert state.get("domains", "greeter")["metadata"]["uid"] != state.get("systems", "greeter")["metadata"]["uid"]
  assert state.list("environments") == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd platform/api && uv run pytest tests/test_crds.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fakes'` (collection error).

- [ ] **Step 3: Move the fake to `tests/fakes.py`, indexed by plural**

Create `platform/api/tests/fakes.py`:

```python
"""In-memory StateWriter/StateReader for API tests: one store per plural, like one CRD per plural."""
import json
from collections import defaultdict

from platform_api.state import ENVIRONMENTS, AlreadyExists, Conflict, NotFound


def _copy(obj: dict) -> dict:
  return json.loads(json.dumps(obj))


class FakeState:
  def __init__(self):
    self.stores = defaultdict(dict)
    self.version = 0
    self.on_create = None
    self.before_delete = None

  @property
  def objects(self) -> dict:
    """The environments store, which test_api.py inspects and mutates directly."""
    return self.stores[ENVIRONMENTS]

  def _bump(self, obj):
    self.version += 1
    obj["metadata"]["resourceVersion"] = str(self.version)

  def create(self, plural, body):
    store = self.stores[plural]
    name = body["metadata"]["name"]
    if name in store:
      raise AlreadyExists(name)
    obj = _copy(body)
    obj["metadata"]["creationTimestamp"] = "2026-10-10T00:00:00Z"
    obj["metadata"]["uid"] = f"uid-{self.version + 1}"
    self._bump(obj)
    store[name] = obj
    created = _copy(obj)
    if self.on_create:
      self.on_create(obj)
    return created

  def replace_status(self, plural, body):
    name = body["metadata"]["name"]
    current = self.stores[plural][name]
    if current["metadata"]["resourceVersion"] != body["metadata"]["resourceVersion"]:
      raise Conflict(name)
    current["status"] = body["status"]
    self._bump(current)
    return _copy(current)

  def delete(self, plural, name, uid=None):
    if self.before_delete:
      self.before_delete(self)
    store = self.stores[plural]
    if name not in store:
      raise NotFound(name)
    if uid is not None and store[name]["metadata"]["uid"] != uid:
      raise Conflict(name)
    del store[name]

  def get(self, plural, name):
    store = self.stores[plural]
    if name not in store:
      raise NotFound(name)
    return _copy(store[name])

  def list(self, plural):
    return [_copy(obj) for obj in self.stores[plural].values()]
```

In `platform/api/tests/test_api.py`, delete the whole `class FakeState:` block (from `class FakeState:` through the end of its `list` method). Replace the import line `from platform_api.state import AlreadyExists, Conflict, NotFound` with `from fakes import FakeState`. Keep the `state` fixture (`return FakeState()`).

In `platform/api/tests/test_auth.py`, change `from test_api import FakeState` to `from fakes import FakeState`.

- [ ] **Step 4: Group per plural in `state.py`**

In `platform/api/src/platform_api/state.py`, replace the constants block:

```python
GROUP = "platform.wasp.silvios.me"
VERSION = "v1alpha1"
ENVIRONMENTS = "environments"
```

with:

```python
GROUP = "platform.wasp.silvios.me"
# Catalog entities live in their own group, apart from the environment and delivery CRDs.
CATALOG_GROUP = f"catalog.{GROUP}"
VERSION = "v1alpha1"
ENVIRONMENTS = "environments"
CATALOG_PLURALS = ("domains", "systems", "resources")


def group_of(plural: str) -> str:
  return CATALOG_GROUP if plural in CATALOG_PLURALS else GROUP
```

Inside `KubeApplyWriter`, replace the first positional argument `GROUP` with `group_of(plural)` in all five calls: `create_namespaced_custom_object`, `replace_namespaced_custom_object_status`, `delete_namespaced_custom_object`, `get_namespaced_custom_object` and `list_namespaced_custom_object`. Check with `grep -n "GROUP, VERSION" platform/api/src/platform_api/state.py`, which must print nothing.

- [ ] **Step 5: Write the three CRDs**

`platform/crds/catalog-domain.yaml`:

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: domains.catalog.platform.wasp.silvios.me
spec:
  group: catalog.platform.wasp.silvios.me
  scope: Namespaced
  names:
    kind: Domain
    listKind: DomainList
    plural: domains
    singular: domain
  versions:
    - name: v1alpha1
      served: true
      storage: true
      additionalPrinterColumns:
        - name: Parent
          type: string
          jsonPath: .spec.parent
        - name: Owner
          type: string
          jsonPath: .spec.owner
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: [owner]
              properties:
                owner:
                  description: Owner team (free text until groups exist in Keycloak, #186).
                  type: string
                  pattern: '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'
                description:
                  type: string
                parent:
                  description: Parent domain; set for a subdomain.
                  type: string
                  pattern: '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'
```

`platform/crds/catalog-system.yaml`:

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: systems.catalog.platform.wasp.silvios.me
spec:
  group: catalog.platform.wasp.silvios.me
  scope: Namespaced
  names:
    kind: System
    listKind: SystemList
    plural: systems
    singular: system
  versions:
    - name: v1alpha1
      served: true
      storage: true
      additionalPrinterColumns:
        - name: Domain
          type: string
          jsonPath: .spec.domain
        - name: Owner
          type: string
          jsonPath: .spec.owner
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: [owner, domain]
              properties:
                owner:
                  description: Owner team (free text until groups exist in Keycloak, #186).
                  type: string
                  pattern: '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'
                description:
                  type: string
                domain:
                  type: string
                  pattern: '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'
```

`platform/crds/catalog-resource.yaml`:

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: resources.catalog.platform.wasp.silvios.me
spec:
  group: catalog.platform.wasp.silvios.me
  scope: Namespaced
  names:
    kind: Resource
    listKind: ResourceList
    plural: resources
    singular: resource
  versions:
    - name: v1alpha1
      served: true
      storage: true
      additionalPrinterColumns:
        - name: Type
          type: string
          jsonPath: .spec.type
        - name: System
          type: string
          jsonPath: .spec.system
        - name: Owner
          type: string
          jsonPath: .spec.owner
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: [owner, type, system]
              properties:
                owner:
                  description: Owner team (free text until groups exist in Keycloak, #186).
                  type: string
                  pattern: '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'
                description:
                  type: string
                type:
                  description: Role of the resource (database, topic, queue, bucket), never a cloud service.
                  type: string
                  pattern: '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'
                system:
                  type: string
                  pattern: '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'
```

- [ ] **Step 6: RBAC for the API ServiceAccount**

In `platform/api/deploy/platform-api.yaml`, under the `Role` `rules:`, after the `environments/status` rule, add:

```yaml
  - apiGroups: [catalog.platform.wasp.silvios.me]
    resources: [domains, systems, resources]
    verbs: [get, list, watch, create, delete]
```

- [ ] **Step 7: Run the whole API suite**

Run: `cd platform/api && uv run pytest -q`
Expected: all pass (48 previous + 5 new).

- [ ] **Step 8: Validate the CRDs against the real API server**

Run: `kubectl --context k3d-platform-local apply --dry-run=server --filename platform/crds/`
Expected: three `customresourcedefinition.apiextensions.k8s.io/<plural>.catalog.platform.wasp.silvios.me created (server dry run)` lines, plus the unchanged `environments` one. If `platform-local` is not running, skip and note it; Task 6 applies the CRDs for real.

- [ ] **Step 9: Commit**

```bash
git add platform/crds platform/api/src/platform_api/state.py platform/api/deploy/platform-api.yaml platform/api/tests
git commit -m "feat(#191): CRDs Domain, System e Resource no grupo catalog e estado por plural

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Catalog model: kinds, request validation, manifest, view and dependents

**Files:**
- Create: `platform/api/src/platform_api/catalog.py`
- Modify: `platform/api/src/platform_api/environments.py` (`is_owner_or_admin` signature)
- Test: `platform/api/tests/test_catalog_model.py`

**Interfaces:**
- Consumes: `state.CATALOG_GROUP`, `state.GROUP`, `state.VERSION` (Task 1), `fakes.FakeState` (Task 1).
- Produces, in `platform_api.catalog`:
  - `Kind` (frozen dataclass: `name`, `plural`, `parent_field`, `parent_plural`, `parent_required`, `required`; property `singular`)
  - `KINDS: dict[str, Kind]`, in the order domains, systems, resources
  - `CREATED_BY_ANNOTATION = "platform.wasp.silvios.me/created-by"`
  - `EntityRequest` (pydantic, `extra="forbid"`)
  - `InvalidRequest(Exception)`
  - `spec_from(kind: Kind, request: EntityRequest) -> dict`
  - `manifest(kind: Kind, name: str, spec: dict, created_by: str) -> dict`
  - `view(kind: Kind, obj: dict) -> dict`
  - `dependents(state, kind: Kind, name: str) -> list[str]`
- Produces, in `platform_api.environments`: `is_owner_or_admin(obj: dict, principal, annotation: str = OWNER_ANNOTATION) -> bool`.

- [ ] **Step 1: Write the failing tests**

`platform/api/tests/test_catalog_model.py`:

```python
import pytest
from pydantic import ValidationError

from fakes import FakeState
from platform_api.catalog import (
  CREATED_BY_ANNOTATION, KINDS, EntityRequest, InvalidRequest, dependents, manifest, spec_from, view,
)
from platform_api.environments import is_owner_or_admin

DOMAINS, SYSTEMS, RESOURCES = KINDS["domains"], KINDS["systems"], KINDS["resources"]


def test_kinds_point_to_their_parent():
  assert (DOMAINS.parent_field, DOMAINS.parent_plural, DOMAINS.parent_required) == ("parent", "domains", False)
  assert (SYSTEMS.parent_field, SYSTEMS.parent_plural, SYSTEMS.parent_required) == ("domain", "domains", True)
  assert (RESOURCES.parent_field, RESOURCES.parent_plural, RESOURCES.required) == ("system", "systems", ("type",))
  assert list(KINDS) == ["domains", "systems", "resources"]


def test_spec_keeps_only_given_fields():
  request = EntityRequest(name="messaging", owner="team-alpha", parent="communication")
  assert spec_from(DOMAINS, request) == {"owner": "team-alpha", "parent": "communication"}


def test_spec_rejects_field_of_other_kind():
  with pytest.raises(InvalidRequest, match="type: not a field of domain"):
    spec_from(DOMAINS, EntityRequest(name="communication", owner="team-alpha", type="database"))
  with pytest.raises(InvalidRequest, match="parent: not a field of system"):
    spec_from(SYSTEMS, EntityRequest(name="greeter", owner="team-alpha", domain="messaging", parent="x"))


def test_spec_requires_parent_and_type():
  with pytest.raises(InvalidRequest, match="domain: required for system"):
    spec_from(SYSTEMS, EntityRequest(name="greeter", owner="team-alpha"))
  with pytest.raises(InvalidRequest, match="type, system: required for resource"):
    spec_from(RESOURCES, EntityRequest(name="greeting-db", owner="team-alpha"))


@pytest.mark.parametrize("field,value", [("name", "Greeter"), ("owner", "group:default/team-alpha"), ("name", "-x"), ("name", "a" * 64)])
def test_request_rejects_invalid_labels(field, value):
  fields = {"name": "greeter", "owner": "team-alpha", field: value}
  with pytest.raises(ValidationError):
    EntityRequest(**fields)


def test_request_rejects_unknown_fields():
  with pytest.raises(ValidationError):
    EntityRequest(name="greeter", owner="team-alpha", lifecycle="production")


def test_manifest_and_view():
  body = manifest(SYSTEMS, "greeter", {"owner": "team-alpha", "domain": "messaging"}, "user-1")
  assert body["apiVersion"] == "catalog.platform.wasp.silvios.me/v1alpha1"
  assert body["kind"] == "System"
  assert body["metadata"] == {"name": "greeter", "annotations": {CREATED_BY_ANNOTATION: "user-1"}}
  obj = {**body, "metadata": {**body["metadata"], "creationTimestamp": "2026-10-10T00:00:00Z"}}
  assert view(SYSTEMS, obj) == {
    "kind": "System", "name": "greeter", "owner": "team-alpha", "description": None,
    "domain": "messaging", "createdAt": "2026-10-10T00:00:00Z",
  }
  resource = manifest(RESOURCES, "greeting-db", {"owner": "team-alpha", "type": "database", "system": "greeter"}, "user-1")
  assert view(RESOURCES, resource)["type"] == "database"


def test_dependents_cover_subdomains_and_systems():
  state = FakeState()
  state.create("domains", manifest(DOMAINS, "communication", {"owner": "a"}, "u"))
  state.create("domains", manifest(DOMAINS, "messaging", {"owner": "a", "parent": "communication"}, "u"))
  state.create("systems", manifest(SYSTEMS, "notifier", {"owner": "a", "domain": "communication"}, "u"))
  state.create("systems", manifest(SYSTEMS, "greeter", {"owner": "a", "domain": "messaging"}, "u"))
  state.create("resources", manifest(RESOURCES, "greeting-db", {"owner": "a", "type": "database", "system": "greeter"}, "u"))
  assert dependents(state, DOMAINS, "communication") == ["domain/messaging", "system/notifier"]
  assert dependents(state, DOMAINS, "messaging") == ["system/greeter"]
  assert dependents(state, SYSTEMS, "greeter") == ["resource/greeting-db"]
  assert dependents(state, RESOURCES, "greeting-db") == []


def test_is_owner_or_admin_reads_the_given_annotation():
  class P:
    sub, groups = "user-1", ["platform-users"]

  obj = {"metadata": {"annotations": {CREATED_BY_ANNOTATION: "user-1"}}}
  assert is_owner_or_admin(obj, P(), CREATED_BY_ANNOTATION)
  assert not is_owner_or_admin(obj, P())
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd platform/api && uv run pytest tests/test_catalog_model.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'platform_api.catalog'`.

- [ ] **Step 3: Generalize `is_owner_or_admin`**

In `platform/api/src/platform_api/environments.py`, replace the function with:

```python
def is_owner_or_admin(obj: dict, principal, annotation: str = OWNER_ANNOTATION) -> bool:
  """True for whoever the annotation names and for platform admins. Environments use the owner
  annotation (kubeconfig and delete); catalog entities pass their created-by annotation. Without the
  annotation (objects created before it existed), only admins pass."""
  person = (obj.get("metadata", {}).get("annotations") or {}).get(annotation)
  return principal.sub == person or ADMIN_GROUP in principal.groups
```

- [ ] **Step 4: Write `catalog.py` (model part)**

`platform/api/src/platform_api/catalog.py`:

```python
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
```

- [ ] **Step 5: Run the tests**

Run: `cd platform/api && uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add platform/api/src/platform_api/catalog.py platform/api/src/platform_api/environments.py platform/api/tests/test_catalog_model.py
git commit -m "feat(#191): modelo do catálogo (kinds, campos por kind, dependentes)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Catalog routes: create, list, get, delete, aggregated list and `catalog: Active`

**Files:**
- Modify: `platform/api/src/platform_api/catalog.py` (append the router)
- Modify: `platform/api/src/platform_api/app.py` (`CAPABILITIES`, `include_router`, import)
- Modify: `platform/api/tests/test_auth.py` (`test_every_v1_route_requires_a_token`, `test_capabilities`)
- Test: `platform/api/tests/test_catalog.py`

**Interfaces:**
- Consumes: everything Task 2 produced; `auth.Principal`, `auth.current_principal`; `journal.Journal.record(action, kind, name, spec, actor) -> str` and `mark_applied(entry_id)`; `state.AlreadyExists`, `NotFound`, `Conflict`.
- Produces: `catalog.router(state, journal) -> fastapi.APIRouter` with these routes, all under `/v1/catalog`:
  - `GET /entities?kind=&owner=`
  - `POST /{plural}` → `201`
  - `GET /{plural}`
  - `GET /{plural}/{name}`, which adds `dependents`
  - `DELETE /{plural}/{name}` → `204`

- [ ] **Step 1: Write the failing tests**

`platform/api/tests/test_catalog.py`:

```python
import json

import pytest
from fastapi.testclient import TestClient

from fakes import FakeState
from platform_api.app import create_app
from platform_api.catalog import CREATED_BY_ANNOTATION
from platform_api.journal import Journal
from tokens import TokenFactory


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


@pytest.fixture
def other(tokens):
  return bearer(tokens, sub="user-2", email="other@example.com")


@pytest.fixture
def tree(client, admin, user):
  """communication > messaging > greeter > greeting-db, the example catalog of the repo."""
  for path, body, headers in [
    ("domains", {"name": "communication", "owner": "team-alpha"}, admin),
    ("domains", {"name": "messaging", "owner": "team-alpha", "parent": "communication"}, admin),
    ("systems", {"name": "greeter", "owner": "team-alpha", "domain": "messaging"}, user),
    ("resources", {"name": "greeting-db", "owner": "team-alpha", "type": "database", "system": "greeter"}, user),
  ]:
    response = client.post(f"/v1/catalog/{path}", json=body, headers=headers)
    assert response.status_code == 201, response.text


def journal(journal_path):
  if not journal_path.exists():
    return []
  return [json.loads(line) for line in journal_path.read_text().splitlines() if "action" in line]


def test_admin_creates_domain_and_subdomain(client, admin):
  client.post("/v1/catalog/domains", json={"name": "communication", "owner": "team-alpha"}, headers=admin)
  response = client.post("/v1/catalog/domains", json={"name": "messaging", "owner": "team-alpha", "parent": "communication"}, headers=admin)
  assert response.status_code == 201
  body = response.json()
  assert (body["kind"], body["name"], body["parent"], body["owner"]) == ("Domain", "messaging", "communication", "team-alpha")


def test_user_cannot_create_domain(client, user):
  response = client.post("/v1/catalog/domains", json={"name": "communication", "owner": "team-alpha"}, headers=user)
  assert response.status_code == 403
  assert response.json()["error"]["code"] == "forbidden"


def test_user_creates_system_and_resource_with_creator(client, state, tree):
  assert state.stores["systems"]["greeter"]["metadata"]["annotations"][CREATED_BY_ANNOTATION] == "user-1"
  assert state.stores["resources"]["greeting-db"]["spec"] == {"owner": "team-alpha", "type": "database", "system": "greeter"}


def test_missing_parent_is_422_and_not_journaled(client, user, journal_path):
  response = client.post("/v1/catalog/systems", json={"name": "greeter", "owner": "team-alpha", "domain": "nope"}, headers=user)
  assert response.status_code == 422
  assert response.json()["error"]["message"] == "system 'greeter': domain 'nope' not found"
  assert journal(journal_path) == []


@pytest.mark.parametrize("path,body,message", [
  ("domains", {"name": "x", "owner": "team-alpha", "type": "database"}, "type: not a field of domain"),
  ("systems", {"name": "x", "owner": "team-alpha"}, "domain: required for system"),
])
def test_fields_per_kind_are_422(client, admin, path, body, message):
  response = client.post(f"/v1/catalog/{path}", json=body, headers=admin)
  assert response.status_code == 422
  assert response.json()["error"]["message"] == message


def test_invalid_name_is_422(client, admin):
  response = client.post("/v1/catalog/domains", json={"name": "Communication", "owner": "team-alpha"}, headers=admin)
  assert response.status_code == 422
  assert response.json()["error"]["code"] == "invalid_request"


def test_duplicate_is_409(client, admin, tree):
  response = client.post("/v1/catalog/domains", json={"name": "communication", "owner": "team-alpha"}, headers=admin)
  assert response.status_code == 409
  assert response.json()["error"]["message"] == "domain 'communication' already exists"


def test_same_name_in_two_kinds(client, admin):
  client.post("/v1/catalog/domains", json={"name": "greeter", "owner": "team-alpha"}, headers=admin)
  response = client.post("/v1/catalog/systems", json={"name": "greeter", "owner": "team-alpha", "domain": "greeter"}, headers=admin)
  assert response.status_code == 201


def test_unknown_kind_is_404(client, admin):
  response = client.get("/v1/catalog/components", headers=admin)
  assert response.status_code == 404
  assert "unknown catalog kind 'components'" in response.json()["error"]["message"]


def test_list_kind_sorted(client, admin, user, tree):
  client.post("/v1/catalog/systems", json={"name": "notifier", "owner": "team-beta", "domain": "communication"}, headers=user)
  items = client.get("/v1/catalog/systems", headers=user).json()["items"]
  assert [(item["name"], item["domain"]) for item in items] == [("greeter", "messaging"), ("notifier", "communication")]


def test_get_shows_dependents(client, user, tree):
  body = client.get("/v1/catalog/domains/communication", headers=user).json()
  assert body["dependents"] == ["domain/messaging"]
  assert client.get("/v1/catalog/systems/greeter", headers=user).json()["dependents"] == ["resource/greeting-db"]
  assert client.get("/v1/catalog/systems/nope", headers=user).status_code == 404


def test_delete_with_dependents_is_409(client, admin, tree):
  response = client.delete("/v1/catalog/systems/greeter", headers=admin)
  assert response.status_code == 409
  assert response.json()["error"]["message"] == "system 'greeter' has dependents: resource/greeting-db"


def test_delete_leaf_then_parent(client, admin, tree):
  for path in ["resources/greeting-db", "systems/greeter", "domains/messaging", "domains/communication"]:
    response = client.delete(f"/v1/catalog/{path}", headers=admin)
    assert response.status_code == 204, f"{path}: {response.text}"
    assert response.content == b""
  assert client.get("/v1/catalog/entities", headers=admin).json()["items"] == []


def test_delete_authorization(client, user, other, admin, tree):
  assert client.delete("/v1/catalog/resources/greeting-db", headers=other).status_code == 403
  assert client.delete("/v1/catalog/resources/greeting-db", headers=user).status_code == 204
  # The admin check comes before the dependents check: a non-admin learns nothing about the tree.
  response = client.delete("/v1/catalog/domains/messaging", headers=user)
  assert response.status_code == 403
  assert response.json()["error"]["message"] == "deleting a domain requires group 'platform-admins'"


def test_journal_records_accepted_requests_only(client, other, admin, tree, journal_path):
  client.delete("/v1/catalog/resources/greeting-db", headers=other)
  client.delete("/v1/catalog/resources/greeting-db", headers=admin)
  entries = journal(journal_path)
  assert [(entry["action"], entry["kind"], entry["name"]) for entry in entries] == [
    ("create", "Domain", "communication"),
    ("create", "Domain", "messaging"),
    ("create", "System", "greeter"),
    ("create", "Resource", "greeting-db"),
    ("delete", "Resource", "greeting-db"),
  ]
  assert entries[2]["actor"] == "user-1 (dev@example.com)"


def test_entities_filters(client, user, tree):
  items = client.get("/v1/catalog/entities", headers=user).json()["items"]
  assert [(item["kind"], item["name"], item["parent"]) for item in items] == [
    ("Domain", "communication", None),
    ("Domain", "messaging", "communication"),
    ("System", "greeter", "messaging"),
    ("Resource", "greeting-db", "greeter"),
  ]
  systems = client.get("/v1/catalog/entities", params={"kind": "system"}, headers=user).json()["items"]
  assert [item["name"] for item in systems] == ["greeter"]
  assert client.get("/v1/catalog/entities", params={"owner": "team-beta"}, headers=user).json()["items"] == []
  assert client.get("/v1/catalog/entities", params={"kind": "component"}, headers=user).status_code == 422
```

In `platform/api/tests/test_auth.py`, change the request line of `test_every_v1_route_requires_a_token` to:

```python
    response = TestClient(app).request(method, path.replace("{name}", "x").replace("{plural}", "domains"))
```

and add to `test_capabilities`:

```python
  assert items["catalog"] == "Active"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd platform/api && uv run pytest tests/test_catalog.py tests/test_auth.py -q`
Expected: FAIL. The catalog routes answer `404` and `test_capabilities` fails on `catalog`.

- [ ] **Step 3: Append the router to `catalog.py`**

Extend the imports at the top of `platform/api/src/platform_api/catalog.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, field_validator

from .auth import Principal, current_principal
from .environments import ADMIN_GROUP, is_owner_or_admin
from .journal import Journal
from .state import CATALOG_GROUP, GROUP, VERSION, AlreadyExists, Conflict, NotFound
```

Append at the end of the file:

```python
def router(state, journal: Journal) -> APIRouter:
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
```

- [ ] **Step 4: Mount the router and flip the capability**

In `platform/api/src/platform_api/app.py`:
- Change `from . import environments` to `from . import catalog, environments`.
- In `CAPABILITIES`, change `"catalog": "NoProviderForCapability",` to `"catalog": "Active",`.
- Just before `return app` at the end of `create_app`, add:

```python
  app.include_router(catalog.router(state, journal))
```

- [ ] **Step 5: Run the whole suite**

Run: `cd platform/api && uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add platform/api/src/platform_api platform/api/tests
git commit -m "feat(#191): rotas /v1/catalog com referências, dependentes, autorização e journal

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: CLI `platform catalog`

**Files:**
- Create: `cli/src/wasp_platform/commands/catalog.py`
- Modify: `cli/src/wasp_platform/client.py` (`_request` handles `204`; five new methods)
- Modify: `cli/src/wasp_platform/cli.py` (register the group)
- Test: `cli/tests/test_catalog.py`

**Interfaces:**
- Consumes: the API routes from Task 3. `output.Format`, `OutputOption`, `print_json`, `print_table`, `success`, `fail`.
- Produces: these `PlatformClient` methods:
  - `create_catalog_entity(plural: str, body: dict) -> dict`
  - `list_catalog(plural: str) -> list[dict]`
  - `get_catalog_entity(plural: str, name: str) -> dict`
  - `delete_catalog_entity(plural: str, name: str) -> None`
  - `list_catalog_entities(kind: str | None = None, owner: str | None = None) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

`cli/tests/test_catalog.py`:

```python
import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app

runner = CliRunner()
KINDS = {"domains": "Domain", "systems": "System", "resources": "Resource"}
PARENTS = {"domains": "parent", "systems": "domain", "resources": "system"}


@pytest.fixture
def api(monkeypatch):
  store = {plural: {} for plural in KINDS}
  requests = []

  def handler(request: httpx.Request) -> httpx.Response:
    requests.append(request)
    parts = request.url.path.split("/")[3:]
    if parts == ["entities"]:
      kind = request.url.params.get("kind")
      items = [
        {**entity, "parent": entity.get(PARENTS[plural])}
        for plural in store for entity in store[plural].values()
        if kind is None or KINDS[plural].lower() == kind
      ]
      return httpx.Response(200, json={"items": items})
    plural = parts[0]
    if request.method == "POST":
      body = json.loads(request.content)
      if body["name"] in store[plural]:
        return httpx.Response(409, json={"error": {"code": "conflict", "message": f"{KINDS[plural].lower()} '{body['name']}' already exists"}})
      store[plural][body["name"]] = {"kind": KINDS[plural], "description": None, **body}
      return httpx.Response(201, json=store[plural][body["name"]])
    if len(parts) == 1:
      return httpx.Response(200, json={"items": list(store[plural].values())})
    name = parts[1]
    if name not in store[plural]:
      return httpx.Response(404, json={"error": {"code": "not_found", "message": f"{KINDS[plural].lower()} '{name}' not found"}})
    if request.method == "GET":
      return httpx.Response(200, json={**store[plural][name], "dependents": []})
    del store[plural][name]
    return httpx.Response(204)

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  return requests


def run(*args):
  return runner.invoke(app, ["catalog", *args])


def test_create_domain_sends_only_given_fields(api):
  result = run("domain", "create", "communication", "--owner", "team-alpha")
  assert result.exit_code == 0, result.output
  assert "✓ domain communication created" in result.output
  assert json.loads(api[-1].content) == {"name": "communication", "owner": "team-alpha"}


def test_create_subdomain_system_and_resource(api):
  run("domain", "create", "messaging", "--parent", "communication", "--owner", "team-alpha")
  assert json.loads(api[-1].content)["parent"] == "communication"
  run("system", "create", "greeter", "--domain", "messaging", "--owner", "team-alpha", "--description", "Greetings")
  assert json.loads(api[-1].content) == {"name": "greeter", "owner": "team-alpha", "domain": "messaging", "description": "Greetings"}
  result = run("resource", "create", "greeting-db", "--type", "database", "--system", "greeter", "--owner", "team-alpha")
  assert "✓ resource greeting-db created" in result.output


def test_required_options_are_enforced_by_cli(api):
  assert run("system", "create", "greeter", "--owner", "team-alpha").exit_code == 2
  assert run("resource", "create", "greeting-db", "--system", "greeter", "--owner", "team-alpha").exit_code == 2


def test_catalog_list_table_and_json(api):
  run("domain", "create", "communication", "--owner", "team-alpha")
  run("system", "create", "greeter", "--domain", "communication", "--owner", "team-alpha")
  lines = run("list").output.splitlines()
  assert lines[0].split() == ["KIND", "NAME", "PARENT", "OWNER"]
  assert lines[1].split() == ["Domain", "communication", "—", "team-alpha"]
  assert lines[2].split() == ["System", "greeter", "communication", "team-alpha"]
  run("list", "--kind", "system")
  assert api[-1].url.params["kind"] == "system"
  assert [item["name"] for item in json.loads(run("list", "--output", "json").output)] == ["communication", "greeter"]


def test_kind_list_columns(api):
  run("resource", "create", "greeting-db", "--type", "database", "--system", "greeter", "--owner", "team-alpha")
  lines = run("resource", "list").output.splitlines()
  assert lines[0].split() == ["NAME", "TYPE", "SYSTEM", "OWNER"]
  assert lines[1].split() == ["greeting-db", "database", "greeter", "team-alpha"]


def test_get_shows_fields_and_dependents(api):
  run("system", "create", "greeter", "--domain", "messaging", "--owner", "team-alpha")
  output = run("system", "get", "greeter").output
  assert output.splitlines()[0] == "system/greeter"
  assert "domain" in output and "messaging" in output
  assert "dependents   none" in output


def test_delete_prints_success(api):
  run("domain", "create", "communication", "--owner", "team-alpha")
  result = run("domain", "delete", "communication")
  assert result.exit_code == 0, result.output
  assert "✓ domain communication deleted" in result.output


def test_api_errors_pass_through(api):
  result = run("system", "delete", "nope")
  assert result.exit_code == 1
  assert "404: system 'nope' not found" in result.output
  run("domain", "create", "communication", "--owner", "team-alpha")
  result = run("domain", "create", "communication", "--owner", "team-alpha")
  assert result.exit_code == 1
  assert "already exists" in result.output
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd cli && uv run pytest tests/test_catalog.py -q`
Expected: FAIL. `catalog` is not a command, so the exit code is 2 (`No such command 'catalog'`).

- [ ] **Step 3: Client methods and `204` handling**

In `cli/src/wasp_platform/client.py`, change the last line of `_request` from `return response.json()` to:

```python
    # 204 (delete) has no body.
    return response.json() if response.content else {}
```

Add after `delete_environment`:

```python
  def create_catalog_entity(self, plural: str, body: dict) -> dict:
    return self._request("POST", f"/v1/catalog/{plural}", json=body)

  def list_catalog(self, plural: str) -> list[dict]:
    return self._request("GET", f"/v1/catalog/{plural}")["items"]

  def get_catalog_entity(self, plural: str, name: str) -> dict:
    return self._request("GET", f"/v1/catalog/{plural}/{name}")

  def delete_catalog_entity(self, plural: str, name: str) -> None:
    self._request("DELETE", f"/v1/catalog/{plural}/{name}")

  def list_catalog_entities(self, kind: str | None = None, owner: str | None = None) -> list[dict]:
    params = {key: value for key, value in {"kind": kind, "owner": owner}.items() if value}
    return self._request("GET", "/v1/catalog/entities", params=params)["items"]
```

- [ ] **Step 4: The command group**

`cli/src/wasp_platform/commands/catalog.py`:

```python
"""The catalog: domains, systems and resources the platform stores (ADR 0023).

Components and APIs live in each repo's catalog-info.yaml and arrive in a later slice.
"""
from enum import Enum
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, print_table, success

app = typer.Typer(help="The catalog: domains, systems and resources.", no_args_is_help=True)

# Table columns of each kind after NAME: (header, field of the API view).
COLUMNS = {
  "domains": [("PARENT", "parent"), ("OWNER", "owner")],
  "systems": [("DOMAIN", "domain"), ("OWNER", "owner")],
  "resources": [("TYPE", "type"), ("SYSTEM", "system"), ("OWNER", "owner")],
}

Owner = Annotated[str, typer.Option(help="Owner team, such as team-alpha.")]
Description = Annotated[str | None, typer.Option(help="One line about it.")]


class Kind(str, Enum):
  domain = "domain"
  system = "system"
  resource = "resource"


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def _cell(value) -> str:
  return value or "—"


def _create(plural: str, singular: str, body: dict, output: Format) -> None:
  try:
    entity = _client().create_catalog_entity(plural, {key: value for key, value in body.items() if value is not None})
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(entity)
  else:
    success(f"{singular} {entity['name']} created")


def _kind_app(plural: str, singular: str, help_text: str) -> typer.Typer:
  """list, get and delete are the same for every kind; create differs and is added per kind."""
  sub = typer.Typer(help=help_text, no_args_is_help=True)

  @sub.command("list", help=f"List {plural}.")
  def list_(output: OutputOption = Format.table):
    try:
      items = _client().list_catalog(plural)
    except ApiError as error:
      fail(str(error))
    if output == Format.json:
      print_json(items)
      return
    headers = ["NAME", *[header for header, _ in COLUMNS[plural]]]
    rows = [[item["name"], *[_cell(item.get(field)) for _, field in COLUMNS[plural]]] for item in items]
    print_table(headers, rows)

  @sub.command("get", help=f"Show a {singular} and what depends on it.")
  def get(name: str, output: OutputOption = Format.table):
    try:
      entity = _client().get_catalog_entity(plural, name)
    except ApiError as error:
      fail(str(error))
    if output == Format.json:
      print_json(entity)
      return
    typer.echo(f"{singular}/{entity['name']}")
    fields = [field for _, field in COLUMNS[plural]] + ["description"]
    for field in fields:
      typer.echo(f"  {field.ljust(12)} {_cell(entity.get(field))}")
    typer.echo(f"  {'dependents'.ljust(12)} {', '.join(entity.get('dependents') or []) or 'none'}")

  @sub.command("delete", help=f"Delete a {singular}; refused while something depends on it.")
  def delete(name: str, output: OutputOption = Format.table):
    try:
      _client().delete_catalog_entity(plural, name)
    except ApiError as error:
      fail(str(error))
    if output == Format.json:
      print_json({"kind": singular, "name": name, "status": "deleted"})
    else:
      success(f"{singular} {name} deleted")

  return sub


domain_app = _kind_app("domains", "domain", "Business areas; --parent makes a subdomain.")
system_app = _kind_app("systems", "system", "Capabilities inside a domain.")
resource_app = _kind_app("resources", "resource", "Infrastructure a system needs, described by its role.")


@domain_app.command("create")
def create_domain(
  name: str,
  owner: Owner,
  parent: Annotated[str | None, typer.Option(help="Parent domain: makes this a subdomain.")] = None,
  description: Description = None,
  output: OutputOption = Format.table,
):
  """Create a domain (platform-admins only)."""
  _create("domains", "domain", {"name": name, "owner": owner, "parent": parent, "description": description}, output)


@system_app.command("create")
def create_system(
  name: str,
  domain: Annotated[str, typer.Option(help="Domain the system belongs to.")],
  owner: Owner,
  description: Description = None,
  output: OutputOption = Format.table,
):
  """Create a system."""
  _create("systems", "system", {"name": name, "owner": owner, "domain": domain, "description": description}, output)


@resource_app.command("create")
def create_resource(
  name: str,
  type_: Annotated[str, typer.Option("--type", help="Role, not a cloud service: database, topic, queue, bucket.")],
  system: Annotated[str, typer.Option(help="System the resource belongs to.")],
  owner: Owner,
  description: Description = None,
  output: OutputOption = Format.table,
):
  """Create a resource shared by the components of a system."""
  _create("resources", "resource", {"name": name, "owner": owner, "type": type_, "system": system, "description": description}, output)


@app.command("list")
def list_all(
  kind: Annotated[Kind | None, typer.Option(help="Only this kind.")] = None,
  owner: Annotated[str | None, typer.Option(help="Only this owner team.")] = None,
  output: OutputOption = Format.table,
):
  """List every entity of the catalog, parents first."""
  try:
    items = _client().list_catalog_entities(kind.value if kind else None, owner)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(items)
    return
  print_table(["KIND", "NAME", "PARENT", "OWNER"], [[item["kind"], item["name"], _cell(item.get("parent")), item["owner"]] for item in items])


app.add_typer(domain_app, name="domain")
app.add_typer(system_app, name="system")
app.add_typer(resource_app, name="resource")
```

In `cli/src/wasp_platform/cli.py`, change `from .commands import environment` to `from .commands import catalog, environment` and add the last line:

```python
app.add_typer(catalog.app, name="catalog")
```

- [ ] **Step 5: Run the whole CLI suite**

Run: `cd cli && uv run pytest -q`
Expected: all pass, including `test_boundaries.py` (`catalog.py` imports nothing from `bootstrap`).

- [ ] **Step 6: Commit**

```bash
git add cli/src/wasp_platform cli/tests/test_catalog.py
git commit -m "feat(#191): platform catalog (domain, system, resource e list)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: ADR 0023 and docs

**Files:**
- Create: `docs/adr/0023-platform-catalog-ownership.md`
- Modify: `docs/adr/README.md` (index row)
- Modify: `platform/api/README.md` (intro sentence, endpoints table, new `## Catálogo` section)
- Modify: `cli/docs/index.md` (new section before `## Referência rápida`, reference rows)
- Modify: `cli/docs/walkthrough.md` (new step before `## 13. Limpar e sair`)

**Interfaces:**
- Consumes: behaviour from Tasks 1–4. The texts below quote its messages exactly.
- Produces: nothing used by code.

- [ ] **Step 1: ADR 0023**

`docs/adr/0023-platform-catalog-ownership.md`:

```markdown
# Platform catalog: organisation entities as CRDs, code entities in the repo, Backstage as reader

**Status:** Aceito (2026-10-10)

## Contexto

O deck apresenta o modelo mental do Backstage como o catálogo da plataforma: Domain e System na visão de negócio; Component, API e Resource na visão de engenharia. Até aqui o catálogo vivia só no Backstage: Domain, System e Resource em arquivos de `idp/catalog/`, Component e API no `catalog-info.yaml` de cada repo (ADR 0020). A Platform API não sabia nada do catálogo.

O ADR 0022 faz da Platform API a fronteira única dos clientes. O catálogo não pode depender do Backstage: se o portal cair, a CLI, a API e os agentes continuam precisando dele.

## Decisão

**Cada entidade do catálogo tem uma casa só, escolhida por onde ela muda; a Platform API é dona das entidades da organização, o repo é dono das entidades de código, e o Backstage lê os dois.**

- **Domain, System e o Resource compartilhado** são CRDs do grupo `catalog.platform.wasp.silvios.me`, criados e apagados pela Platform API (`platform catalog <kind> create`). Não pertencem a nenhum repo.
- **Component e API** ficam no `catalog-info.yaml` (e no `openapi.yaml`) do repo e mudam no mesmo PR que o código. A plataforma os cria pelo golden path (`platform catalog component create --type service`) e depois os descobre.
- **"Catalog" é o espaço de nomes** (grupo de CRDs, `/v1/catalog`, `platform catalog`), não uma entidade que contém as outras.
- **Resource do catálogo é a identidade lógica, descrita pelo papel** ("o banco do greeter"), uma só para todos os ambientes. A instância num ambiente é um `ResourceRequest` (ADR 0022) e não entra no catálogo.
- **O Score liga a app ao catálogo pelo `resources.<nome>.id`.** Sem `id`, o recurso é só da app e o resolvedor deriva o Resource (`<component>-<nome>`). Com `id`, ele aponta para um Resource compartilhado já cadastrado, e um `id` inexistente é recusado no build.
- **O resolvedor do ADR 0022 chama-se Forager**: lê o Score do release, resolve cada recurso contra o catálogo e a `BindingPolicy` do ambiente, e cria ou reaproveita o `ResourceRequest`.
- **O Backstage lê a Platform API** (entity provider) e o discovery da org (ADR 0020). Nenhum dos dois depende do outro para funcionar.
- **Owner é texto livre** (nome do time) até os grupos de time existirem no Keycloak (#186).

## Consequências

- Backstage fora do ar não afeta a CLI, a API nem os agentes. Platform API fora do ar deixa o portal com a última leitura.
- `idp/catalog/` vira carga inicial, importada pelo `platform catalog import` (#190), e deixa de ser location do Backstage quando o entity provider existir.
- O dev pede um tipo (`postgres`) no Score, não escolhe um Resource da plataforma; o banco compartilhado da plataforma aparece no catálogo como Resource de `team-platform`, alvo do modo `compose`.
- A checagem de dependentes antes de apagar não é atômica; um finalizer no pai fecha a brecha quando o volume justificar.
- Os comandos ilustrativos do deck passam de `platform app …` para `platform catalog component …`, e o ciclo de vida usa `--component`.
```

In `docs/adr/README.md`, append after the `0022` row:

```markdown
| [0023](0023-platform-catalog-ownership.md) | Catálogo da plataforma: Domain, System e Resource como CRDs, Component e API no repo, Backstage como leitor; resolvedor Forager |
```

- [ ] **Step 2: `platform/api/README.md`**

Replace the intro sentence's end `com uma ServiceAccount que só enxerga \`environments\` no namespace \`platform-system\`.` with `com uma ServiceAccount que só enxerga \`environments\` e as entidades do catálogo (\`domains\`, \`systems\`, \`resources\`) no namespace \`platform-system\`.`

Append to the endpoints table, after the `DELETE /v1/environments/{name}` row:

```markdown
| `POST` | `/v1/catalog/{kind}` | `201`; `kind` é `domains`, `systems` ou `resources`; body `{"name", "owner", "description", "parent"\|"domain"\|"system", "type"}` |
| `GET` | `/v1/catalog/{kind}` | `200`, `{"items": [...]}` |
| `GET` | `/v1/catalog/{kind}/{name}` | `200`, com `dependents` |
| `DELETE` | `/v1/catalog/{kind}/{name}` | `204`; `409` enquanto houver dependentes |
| `GET` | `/v1/catalog/entities` | `200`, todos os kinds com `parent` normalizado; filtros `?kind=domain\|system\|resource` e `?owner=` |
```

Add this section before `## Escrita`:

```markdown
## Catálogo

Domain, System e Resource são CRDs do grupo `catalog.platform.wasp.silvios.me` (ADR 0023). Component e API não passam por aqui: ficam no `catalog-info.yaml` do repo.

| Kind | Pai | Obrigatórios |
|---|---|---|
| `Domain` | `parent` (outro Domain; opcional, faz um subdomínio) | `owner` |
| `System` | `domain` | `owner`, `domain` |
| `Resource` | `system` | `owner`, `type` (papel: `database`, `topic`…), `system` |

- O pai precisa existir no create; senão `422` (`system 'greeter': domain 'nope' not found`). Campo de outro kind ou faltando também é `422`.
- Apagar com dependentes é `409` com a lista (`system 'greeter' has dependents: resource/greeting-db`).
- Domain: create e delete só para `platform-admins`. System e Resource: qualquer usuário autenticado cria; só quem criou (anotação `platform.wasp.silvios.me/created-by`) ou `platform-admins` apaga. O `owner` é o time e é texto livre até a #186; quem criou é a pessoa.
- Create e delete aceitos entram no journal; os negados, não. O delete leva o `uid` como precondição, como no Environment.
```

- [ ] **Step 3: `cli/docs/index.md`**

`Desmontar tudo` must stay the last numbered section. Insert the new section right before `## 11. Desmontar tudo` as `## 11. Catálogo`, and renumber `Desmontar tudo` to `## 12. Desmontar tudo`:

````markdown
## 11. Catálogo

Domínios, sistemas e recursos que a plataforma guarda. Domínio só `platform-admins` cria; sistema e recurso, qualquer usuário.

```bash
platform catalog domain create communication --owner team-alpha
platform catalog domain create messaging --parent communication --owner team-alpha
platform catalog system create greeter --domain messaging --owner team-alpha
platform catalog resource create greeting-db \
  --type database \
  --system greeter \
  --owner team-alpha
platform catalog list
```

```
KIND      NAME           PARENT         OWNER
Domain    communication  —              team-alpha
Domain    messaging      communication  team-alpha
System    greeter        messaging      team-alpha
Resource  greeting-db    greeter        team-alpha
```

Apagar é na ordem inversa: com dependentes, a API recusa e diz quais são.

```bash
platform catalog domain delete messaging
```

```
✗ 409: domain 'messaging' has dependents: system/greeter
```

O `--type` do recurso é o papel (`database`, `topic`, `queue`, `bucket`), nunca o serviço de nuvem. Componentes e APIs ainda não estão no catálogo da plataforma.
````

Add to the `## Referência rápida` table, after the `platform environment delete` row:

```markdown
| `platform catalog domain create <nome> --owner <time> [--parent <domínio>]` | cria um domínio ou subdomínio (só `platform-admins`) |
| `platform catalog system create <nome> --domain <domínio> --owner <time>` | cria um sistema |
| `platform catalog resource create <nome> --type <papel> --system <sistema> --owner <time>` | cria um recurso compartilhado |
| `platform catalog list [--kind domain\|system\|resource] [--owner <time>]` | KIND, NAME, PARENT, OWNER |
| `platform catalog <kind> list\|get\|delete` | por kind; `get` mostra os dependentes |
```

- [ ] **Step 4: `cli/docs/walkthrough.md`**

Insert before `## 13. Limpar e sair`, and renumber `Limpar e sair` to `## 14.`. Then run `grep -n "passo 1[34]" cli/docs/walkthrough.md` and fix any reference that pointed to the old number.

````markdown
## 13. Catálogo

```bash
platform catalog domain create communication --owner team-alpha
platform catalog domain create messaging --parent communication --owner team-alpha
platform catalog system create greeter --domain messaging --owner team-alpha
platform catalog resource create greeting-db --type database --system greeter --owner team-alpha
platform catalog list
platform catalog system get greeter
platform catalog domain delete messaging
kubectl --context k3d-platform-local --namespace platform-system get domains.catalog.platform.wasp.silvios.me
```

```
system/greeter
  domain       messaging
  owner        team-alpha
  description  —
  dependents   resource/greeting-db
✗ 409: domain 'messaging' has dependents: system/greeter
NAME            PARENT          OWNER
communication                   team-alpha
messaging       communication   team-alpha
```

Funciona com o Backstage parado: o catálogo é da plataforma. Para limpar, na ordem inversa:

```bash
platform catalog resource delete greeting-db
platform catalog system delete greeter
platform catalog domain delete messaging
platform catalog domain delete communication
```
````

- [ ] **Step 5: Commit**

```bash
git add docs/adr platform/api/README.md cli/docs
git commit -m "docs(#191): ADR 0023 do catálogo e guias da API e da CLI

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: End to end on `platform-local` with the Backstage stopped, then PR

**Files:**
- Modify: `cli/docs/walkthrough.md` (only if the real output differs from Task 5's text)

**Interfaces:**
- Consumes: all previous tasks.
- Produces: the PR closing #191.

- [ ] **Step 1: Confirm the Backstage is down**

Run: `curl --silent --output /dev/null --write-out '%{http_code}\n' http://localhost:7007/ || true`
Expected: `000`. If something answers, ask the user before stopping it.

- [ ] **Step 2: Deploy the new CRDs, API and RBAC**

Run: `source ~/.credentials/bash_gcp_idp && (cd cli && uv run platform init --target local)`
Expected: ends with `✓ Platform API at http://127.0.0.1:9090`. The theme did not change, so Keycloak does not restart.

- [ ] **Step 3: Session**

Run: `(cd cli && uv run platform whoami)`. If it prints `not logged in`, start `nohup uv run platform login --use-device-code > /tmp/platform-login.log 2>&1 < /dev/null &` inside `cli/`, give the user the URL from the log, and wait for `✓ Logged in`. The user must be in `platform-admins` to create domains.

- [ ] **Step 4: Run the walkthrough step 13 commands**

Run the commands of `## 13. Catálogo` from `cli/docs/walkthrough.md` in order, from `cli/` with `uv run platform …`.
Expected: the outputs written in Task 5, including the `409` on `domain delete messaging` and the `kubectl get` columns. If real output differs (column spacing, order), update the walkthrough text to the real output.

- [ ] **Step 5: Journal shows the catalog**

Run: `kubectl --context k3d-platform-local --namespace platform-system exec deploy/platform-api -- tail -n 8 /var/lib/platform/journal.jsonl`
Expected: `create` lines with `"kind":"Domain"`, `"System"` and `"Resource"`, each followed by its `applied: true` line.

- [ ] **Step 6: Clean up in reverse order**

Run the four deletes from the walkthrough, then `uv run platform catalog list`.
Expected: four `✓ … deleted` lines and an empty table (header only).

- [ ] **Step 7: Full suites once more**

Run: `(cd platform/api && uv run pytest -q) && (cd cli && uv run pytest -q)`
Expected: all pass.

- [ ] **Step 8: Commit any walkthrough fix, push and open the PR**

```bash
git add cli/docs/walkthrough.md && git commit -m "docs(#191): saída real do passo de catálogo no walkthrough

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" || true
git push --set-upstream origin feat/191-catalog-domain-system-resource
```

Write `/tmp/feat-191-catalog-domain-system-resource-pr.txt` (markdown, repo-relative paths, ending with `Closes #191` and the line `🤖 Generated with [Claude Code](https://claude.com/claude-code)`). It must summarize:
- the model, pointing to the spec and ADR 0023;
- what the API and the CLI gained;
- the tests, with their counts;
- the end-to-end run with the Backstage stopped;
- the accepted non-atomic dependents check.

Then run:

```bash
gh pr create --base main --head feat/191-catalog-domain-system-resource \
  --title "feat(#191): catálogo da plataforma — Domain, System e Resource na API e na CLI" \
  --body-file /tmp/feat-191-catalog-domain-system-resource-pr.txt
```

Leave a comment on #191 with the PR link and the state. `HANDOFF.md` is updated after the merge, in a separate `docs/191-handoff` PR, the same way as #185.
