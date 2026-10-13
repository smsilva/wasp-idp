"""Workload Instances (#292, ADR 0033): a version from the index deployed in an Environment.

The API writes WorkloadRevisions (and WorkloadRoutes, below), never the vcluster. A revision is named
<environment>.<instance>.<n>: the number is the newest plus one, so two concurrent requests collide on the name and the second gets a 409 (optimistic
concurrency, no lock). The workload provider applies the newest revision in the vcluster and keeps
the WorkloadInstance, the runtime view. Writing needs can_use on the environment and the component's
owner team (or platform-admins); reading needs can_use. An instance is named after its component by
default; an extra one (#294, the shared sandbox) names its component on the first deploy, and keeps it
for as long as its history lives: a deploy that names another one is a 409. A rollback is a new revision
with the version and overrides of an earlier one; a remove is a revision too, and the history stays
until the environment goes.

apply (#293) takes the plan of an environment (the helmfile of its instances) and diffs it against the
newest revision of each instance: one revision per instance that changes, and with prune a remove for
each instance the plan leaves out. Every instance is authorized and resolved before the first write.

A route (#344, ADR 0035) splits the traffic to a component's Service among its instances: one
WorkloadRoute per component and environment, named <environment>.<component>, written whole on every
PUT (last write wins: two clients that read and write at the same time keep the second one's rules).
The workload provider turns it into a GAMMA HTTPRoute. While a route sends traffic to an instance, or
the route exists at all for the main one (its parentRef), removing that instance is a 409.
"""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .auth import Principal, current_principal
from .builds import COMPONENTS, VERSION_PATTERN, VERSIONS
from .catalog import LABEL
from .environments import ADMIN_GROUP, can_use, no_vcluster
from .journal import Journal
from .state import ENVIRONMENTS, GROUP, VERSION, AlreadyExists, Conflict, NotFound

REVISIONS = "workloadrevisions"
INSTANCES = "workloadinstances"
ROUTES = "workloadroutes"
KIND = "WorkloadRevision"
ROUTE_KIND = "WorkloadRoute"
ENVIRONMENT_LABEL = f"{GROUP}/environment"
COMPONENT_LABEL = f"{GROUP}/component"
INSTANCE_LABEL = f"{GROUP}/instance"
# Ready=Unknown: the provider has not closed the revision yet.
OPEN = "Unknown"
MAX_PLAN = 100
# Without the override the provider runs one replica.
DEFAULT_REPLICAS = 1
MAX_RESOURCE_CLASSES = 16
MAX_RULES = 16
# A header name (an HTTP token without the rarer symbols), and a header or baggage value: the provider
# puts the baggage ones in an RE2 regular expression, so anything wider would need escaping there.
HEADER_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}")
MATCH_VALUE = re.compile(r"[A-Za-z0-9._-]{1,64}")


class RevisionRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  # By default the one the instance already runs, else the one named like the instance.
  component: str | None = None
  version: str | None = None
  branch: str | None = None
  replicas: int | None = Field(default=None, ge=0, le=20)
  # resource -> class: the branch picks an item of the environment policy, never a credential (#306).
  resourceClasses: dict[str, str] | None = Field(default=None, max_length=MAX_RESOURCE_CLASSES)
  # A rollback copies the version and the overrides of that revision of the same instance.
  rollbackTo: int | None = Field(default=None, ge=1)

  @field_validator("version")
  @classmethod
  def check_version(cls, value: str | None) -> str | None:
    if value is not None and not VERSION_PATTERN.fullmatch(value):
      raise ValueError("<major>.<minor>.<patch>[-<pre-release>], e.g. 1.0.0-rc.1")
    return value

  @field_validator("resourceClasses")
  @classmethod
  def check_classes(cls, value: dict[str, str] | None) -> dict[str, str] | None:
    for name, klass in (value or {}).items():
      for item in (name, klass):
        if not LABEL.fullmatch(item):
          raise ValueError(f"'{item}' is not a valid name")
    return value


class PlanEntry(BaseModel):
  model_config = ConfigDict(extra="forbid")

  # By default the key: an extra instance names its component (#294).
  component: str | None = None
  version: str | None = None
  branch: str | None = None
  replicas: int | None = Field(default=None, ge=0, le=20)
  resourceClasses: dict[str, str] | None = Field(default=None, max_length=MAX_RESOURCE_CLASSES)

  check_version = field_validator("version")(RevisionRequest.check_version.__func__)
  check_classes = field_validator("resourceClasses")(RevisionRequest.check_classes.__func__)


class ApplyRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  workloads: dict[str, PlanEntry] = Field(max_length=MAX_PLAN)
  dryRun: bool = True
  prune: bool = False


class HeaderMatch(BaseModel):
  model_config = ConfigDict(extra="forbid")

  name: str
  value: str

  @field_validator("name")
  @classmethod
  def check_name(cls, value: str) -> str:
    if not HEADER_NAME.fullmatch(value):
      raise ValueError("letters, digits and '-', up to 63 characters")
    return value

  @field_validator("value")
  @classmethod
  def check_value(cls, value: str) -> str:
    if not MATCH_VALUE.fullmatch(value):
      raise ValueError("letters, digits, '.', '_' and '-', up to 64 characters")
    return value


class BaggageMatch(BaseModel):
  model_config = ConfigDict(extra="forbid")

  key: str
  value: str

  check_key = field_validator("key")(HeaderMatch.check_value.__func__)
  check_value = field_validator("value")(HeaderMatch.check_value.__func__)


class Match(BaseModel):
  model_config = ConfigDict(extra="forbid")

  header: HeaderMatch | None = None
  baggage: BaggageMatch | None = None

  @model_validator(mode="after")
  def one_of(self) -> "Match":
    if (self.header is None) == (self.baggage is None):
      raise ValueError("give either header or baggage")
    return self


class RouteRule(BaseModel):
  model_config = ConfigDict(extra="forbid")

  match: Match | None = None
  to: str | None = None
  weights: dict[str, int] | None = Field(default=None, min_length=1, max_length=MAX_RULES)

  @model_validator(mode="after")
  def one_of(self) -> "RouteRule":
    if self.weights is None and (self.match is None or self.to is None):
      raise ValueError("give either match and to, or weights")
    if self.weights is not None and (self.match is not None or self.to is not None):
      raise ValueError("a weights rule takes no match nor to")
    for weight in (self.weights or {}).values():
      if not 1 <= weight <= 100:
        raise ValueError("each weight is a percentage from 1 to 100")
    return self


class RouteRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  rules: list[RouteRule] = Field(min_length=1, max_length=MAX_RULES)


def match_of(rule: dict) -> tuple | None:
  """What a rule matches on, to compare two rules: ("header", name, value), ("baggage", key, value), or
  None for the weights rule. Header names are case-insensitive."""
  match = rule.get("match") or {}
  if match.get("header"):
    return ("header", match["header"]["name"].lower(), match["header"]["value"])
  if match.get("baggage"):
    return ("baggage", match["baggage"]["key"], match["baggage"]["value"])
  return None


def routed(rules: list[dict]) -> set[str]:
  """The instances the rules send traffic to."""
  return {rule["to"] for rule in rules if rule.get("to")} | {name for rule in rules for name in rule.get("weights") or {}}


def traffic_of(instance: str, component: str, route: dict | None) -> str | None:
  """How the route sends traffic to the instance, for the TRAFFIC column: x-sandbox=pr-42,
  baggage sandbox=pr-42, 10%; default for the main instance that only takes what no rule matched."""
  if route is None:
    return None
  labels = []
  for rule in route["spec"].get("rules") or []:
    match = rule.get("match") or {}
    if rule.get("to") == instance and match.get("header"):
      labels.append(f"{match['header']['name']}={match['header']['value']}")
    elif rule.get("to") == instance and match.get("baggage"):
      labels.append(f"baggage {match['baggage']['key']}={match['baggage']['value']}")
    elif instance in (rule.get("weights") or {}):
      labels.append(f"{rule['weights'][instance]}%")
  if not labels and instance == component:
    return "default"
  return ", ".join(labels) or None


def route_view(obj: dict) -> dict:
  spec = obj.get("spec", {})
  ready = ready_of(obj)
  return {
    "kind": ROUTE_KIND,
    "name": obj["metadata"]["name"],
    "environment": spec.get("environment"),
    "component": spec.get("component"),
    "rules": spec.get("rules") or [],
    "status": (ready or {}).get("reason") or "Pending",
    "message": (ready or {}).get("message"),
  }


def ready_of(obj: dict) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), None)


def is_open(revision: dict) -> bool:
  ready = ready_of(revision)
  return ready is None or ready.get("status") == OPEN


def resource_classes(spec: dict) -> dict[str, str]:
  resources = (spec.get("overrides") or {}).get("resources") or {}
  return {name: item["class"] for name, item in sorted(resources.items()) if item.get("class")}


def overrides_of(replicas: int | None, classes: dict[str, str] | None) -> dict:
  overrides = {}
  if replicas is not None:
    overrides["replicas"] = replicas
  if classes:
    overrides["resources"] = {name: {"class": klass} for name, klass in sorted(classes.items())}
  return overrides


def revision_view(obj: dict) -> dict:
  spec = obj.get("spec", {})
  status = obj.get("status") or {}
  ready = ready_of(obj)
  return {
    "kind": KIND,
    "name": obj["metadata"]["name"],
    **{field: spec.get(field) for field in ("environment", "instance", "component", "revision", "action", "version", "image", "digest", "commit", "requestedBy", "rollbackOf")},
    "replicas": (spec.get("overrides") or {}).get("replicas"),
    "resourceClasses": resource_classes(spec),
    "status": (ready or {}).get("reason") or "Pending",
    "open": is_open(obj),
    "message": (ready or {}).get("message"),
    "startedAt": status.get("startedAt"),
    "finishedAt": status.get("finishedAt"),
    "createdAt": obj["metadata"].get("creationTimestamp"),
  }


def instance_view(environment: str, instance: str, obj: dict | None, latest: dict) -> dict:
  """The instance as the provider last saw it, and the newest revision: right after a deploy the
  instance may not exist yet, or still run the previous revision."""
  status = (obj or {}).get("status") or {}
  ready = ready_of(obj) if obj else None
  replicas = status.get("replicas") or {}
  return {
    "kind": "WorkloadInstance",
    "name": f"{instance}@{environment}",
    "environment": environment,
    "instance": instance,
    "component": ((obj or {}).get("spec") or {}).get("component") or latest["spec"].get("component"),
    "version": status.get("version"),
    "image": status.get("image"),
    "revision": status.get("revision"),
    "status": (ready or {}).get("reason") or "Pending",
    "message": (ready or {}).get("message"),
    "replicas": {"desired": replicas.get("desired"), "ready": replicas.get("ready")} if replicas else None,
    "url": status.get("url"),
    "publicUrl": status.get("publicUrl"),
    "traffic": None,
    "resources": [{key: item.get(key) for key in ("name", "type", "mode", "status")} for item in status.get("resources") or []],
    "latestRevision": revision_view(latest),
  }


def router(state, journal: Journal) -> APIRouter:
  routes = APIRouter(prefix="/v1/environments/{environment}")

  def usable(environment: str, principal: Principal) -> dict:
    try:
      obj = state.get(ENVIRONMENTS, environment)
    except NotFound:
      raise HTTPException(404, f"environment '{environment}' not found")
    if not can_use(obj, principal):
      raise HTTPException(403, f"environment '{environment}' is not yours nor shared with your teams")
    return obj

  def writable(environment: str, principal: Principal) -> dict:
    """usable, and with a vcluster to write workloads to: an environment in a cloud account has none (#435)."""
    obj = usable(environment, principal)
    if reason := no_vcluster(obj):
      raise HTTPException(409, reason)
    return obj

  def revisions_of(environment: str, instance: str | None = None, component: str | None = None) -> list[dict]:
    items = [
      obj for obj in state.list(REVISIONS)
      if obj["spec"].get("environment") == environment
      and (instance is None or obj["spec"].get("instance") == instance)
      and (component is None or obj["spec"].get("component") == component)
    ]
    return sorted(items, key=lambda obj: (obj["spec"]["instance"], obj["spec"]["revision"]))

  def instances_of(environment: str) -> list[dict]:
    """One view per instance: those the provider keeps, and those whose first revision is still open.
    A closed revision with no instance behind it (a failed first deploy, a remove) shows nothing."""
    latest: dict[str, dict] = {}
    for obj in revisions_of(environment):
      latest[obj["spec"]["instance"]] = obj
    kept = {obj["spec"]["instance"]: obj for obj in state.list(INSTANCES) if obj["spec"].get("environment") == environment}
    routes = routes_of(environment)
    views = []
    for instance, revision in sorted(latest.items()):
      obj = kept.get(instance)
      if obj is None and not is_open(revision):
        continue
      view = instance_view(environment, instance, obj, revision)
      view["traffic"] = traffic_of(instance, view["component"], routes.get(view["component"]))
      views.append(view)
    return views

  def routes_of(environment: str) -> dict[str, dict]:
    return {obj["spec"]["component"]: obj for obj in state.list(ROUTES) if obj["spec"].get("environment") == environment}

  def check_unrouted(environment: str, instance: str, component: str, act: str) -> None:
    """A 409 while a route sends traffic to the instance, or is attached to it (the main instance)."""
    route = routes_of(environment).get(component)
    if route is None:
      return
    if instance in routed(route["spec"].get("rules") or []):
      raise HTTPException(409, f"{act} of {instance}@{environment}: the route of '{component}' sends traffic to it; change the route first")
    if instance == component:
      raise HTTPException(409, f"{act} of {instance}@{environment}: it is the main instance of the route of '{component}'; clear the route first")

  def resolve(component: str, request: RevisionRequest) -> dict:
    versions = [obj for obj in state.list(VERSIONS) if obj["spec"].get("component") == component]
    if request.version is not None:
      found = [obj for obj in versions if obj["spec"].get("version", "").lower() == request.version.lower()]
      wanted = f"version {request.version}"
    else:
      found = [obj for obj in versions if obj["spec"].get("branch") == request.branch]
      wanted = f"version built from branch '{request.branch}'"
    if not found:
      raise HTTPException(404, f"deploy of '{component}': no {wanted} in the index")
    newest = max(found, key=lambda obj: (obj["spec"].get("createdAt") or "", obj["metadata"]["name"]))
    if newest["spec"].get("appSpec") is None:
      raise HTTPException(409, f"SpecNotIndexed: {component} {newest['spec'].get('version')} was indexed before the version index kept the spec: build it again under a new version")
    return newest

  def component_of(environment: str, instance: str, asked: str | None) -> str:
    """The component an instance runs: the one of its revisions, else the one asked for, else its name."""
    existing = revisions_of(environment, instance)
    if not existing:
      if asked is None or asked == instance:
        return instance
      # The Service takes the instance name: an extra instance named like another component would answer
      # for it (http://<component>) in the environment.
      try:
        state.get(COMPONENTS, instance)
      except NotFound:
        return asked
      raise HTTPException(409, f"'{instance}' is the name of another component: an instance of '{asked}' cannot take it")
    current = existing[-1]["spec"]["component"]
    if asked is not None and asked != current:
      raise HTTPException(409, f"{instance}@{environment} runs component '{current}', not '{asked}': give the other one an instance of its own")
    return current

  def authorize(environment: str, instance: str, principal: Principal, act: str, asked: str | None = None) -> tuple[dict, str]:
    """The environment and the component, for a principal who may write revisions of the instance."""
    if not LABEL.fullmatch(instance):
      raise HTTPException(422, f"'{instance}' is not an instance name")
    if asked is not None and not LABEL.fullmatch(asked):
      raise HTTPException(422, f"'{asked}' is not a component name")
    env = writable(environment, principal)
    component = component_of(environment, instance, asked)
    check_owner(component, principal, act)
    return env, component

  def check_owner(component: str, principal: Principal, act: str) -> None:
    try:
      owner = (state.get(COMPONENTS, component).get("spec") or {}).get("owner")
    except NotFound:
      raise HTTPException(404, f"component '{component}' not found")
    if not (owner in principal.teams or ADMIN_GROUP in principal.groups):
      raise HTTPException(403, f"{act} of '{component}': only members of its owner team ({owner or 'none'}) and {ADMIN_GROUP} {act} it")

  def write(env: dict, instance: str, component: str, spec: dict, principal: Principal) -> dict:
    """Revision <newest + 1>: a concurrent request that took the number first makes this one a 409."""
    environment = env["metadata"]["name"]
    existing = revisions_of(environment, instance)
    number = existing[-1]["spec"]["revision"] + 1 if existing else 1
    spec = {
      "environment": environment,
      "instance": instance,
      "component": component,
      "revision": number,
      **spec,
      "requestedBy": principal.email or principal.sub,
      "requestId": str(uuid.uuid4()),
    }
    name = f"{environment}.{instance}.{number}"
    entry = journal.record("create", KIND, name, spec, principal.actor)
    body = {
      "apiVersion": f"{GROUP}/{VERSION}",
      "kind": KIND,
      "metadata": {
        "name": name,
        "labels": {ENVIRONMENT_LABEL: environment, COMPONENT_LABEL: component, INSTANCE_LABEL: instance},
        # The history goes with the environment, and outlives a remove of the instance.
        "ownerReferences": [{"apiVersion": f"{GROUP}/{VERSION}", "kind": "Environment", "name": environment, "uid": env["metadata"]["uid"]}],
      },
      "spec": spec,
    }
    try:
      created = state.create(REVISIONS, body)
    except AlreadyExists:
      raise HTTPException(409, f"revision {number} of {instance}@{environment} was taken by a concurrent request: try again")
    journal.mark_applied(entry)
    return revision_view(created)

  def check_resources(verb: str, instance: str, version: dict, classes: dict[str, str] | None) -> None:
    resources = version["spec"]["appSpec"].get("resources") or {}
    for name in sorted(classes or {}):
      if name not in resources:
        raise HTTPException(422, f"{verb} of '{instance}': {version['spec']['version']} has no resource '{name}' to give a class")

  def wanted(revision: dict) -> dict:
    view = {"version": revision["version"], "replicas": DEFAULT_REPLICAS if revision["replicas"] is None else revision["replicas"]}
    if revision.get("resourceClasses"):
      view["resourceClasses"] = revision["resourceClasses"]
    return view

  def live(environment: str) -> dict[str, dict]:
    """The newest revision of each instance that runs or is on its way: a remove, or a failed first
    deploy, leaves nothing to diff against."""
    return {view["instance"]: view["latestRevision"] for view in instances_of(environment) if view["latestRevision"]["action"] != "remove"}

  def plan_of(environment: str, request: "ApplyRequest", principal: Principal) -> tuple[dict, list[dict]]:
    """The environment and one item per instance of the plan, and with prune per instance left out.
    Raises before anything is written when one cannot be applied."""
    env = writable(environment, principal)
    newest = live(environment)
    items = []
    for instance, entry in sorted(request.workloads.items()):
      if (entry.version is None) == (entry.branch is None):
        raise HTTPException(422, f"apply of '{instance}': give either version or branch")
      # The plan names the component of every instance: without component, the key.
      _, component = authorize(environment, instance, principal, "deploy", entry.component or instance)
      version = resolve(component, RevisionRequest(version=entry.version, branch=entry.branch))
      check_resources("apply", instance, version, entry.resourceClasses)
      to = {"version": version["spec"]["version"], "replicas": entry.replicas if entry.replicas is not None else DEFAULT_REPLICAS}
      if entry.resourceClasses:
        to["resourceClasses"] = dict(sorted(entry.resourceClasses.items()))
      current = newest.get(instance)
      if current is None:
        action = "add"
      # An open revision is on its way; a failed one is tried again.
      elif wanted(current) == to and (current["open"] or current["status"] == "Succeeded"):
        action = "unchanged"
      else:
        action = "change"
      spec = {"action": "deploy", **{field: version["spec"][field] for field in ("version", "image", "digest")}}
      if version["spec"].get("commit"):
        spec["commit"] = version["spec"]["commit"]
      overrides = overrides_of(entry.replicas, entry.resourceClasses)
      if overrides:
        spec["overrides"] = overrides
      items.append({"instance": instance, "component": component, "action": action, "from": wanted(current) if current else None, "to": to, "spec": spec})
    if request.prune:
      for instance, current in sorted(newest.items()):
        if instance in request.workloads:
          continue
        _, component = authorize(environment, instance, principal, "remove")
        check_unrouted(environment, instance, component, "prune")
        items.append({"instance": instance, "component": component, "action": "remove", "from": wanted(current), "to": None, "spec": {"action": "remove"}})
    return env, items

  def rollback_source(environment: str, instance: str, number: int) -> dict:
    try:
      source = state.get(REVISIONS, f"{environment}.{instance}.{number}")
    except NotFound:
      raise HTTPException(404, f"rollback of {instance}@{environment}: revision {number} not found")
    if source["spec"].get("action") == "remove":
      raise HTTPException(409, f"rollback of {instance}@{environment}: revision {number} is a remove")
    if (ready_of(source) or {}).get("reason") != "Succeeded":
      raise HTTPException(409, f"rollback of {instance}@{environment}: revision {number} did not succeed ({revision_view(source)['status']})")
    return source

  @routes.post("/workloads/{instance}/revisions", status_code=202)
  def create(environment: str, instance: str, request: RevisionRequest, principal: Principal = Depends(current_principal)):
    if request.rollbackTo is not None:
      if request.version is not None or request.branch is not None or request.replicas is not None or request.resourceClasses or request.component is not None:
        raise HTTPException(422, f"rollback of '{instance}': rollbackTo takes the version and overrides of that revision, give nothing else")
      env, component = authorize(environment, instance, principal, "rollback")
      source = rollback_source(environment, instance, request.rollbackTo)["spec"]
      spec = {"action": "rollback", "rollbackOf": request.rollbackTo, **{field: source[field] for field in ("version", "image", "digest", "commit", "overrides") if field in source}}
      return write(env, instance, component, spec, principal)
    if (request.version is None) == (request.branch is None):
      raise HTTPException(422, f"deploy of '{instance}': give either version or branch")
    env, component = authorize(environment, instance, principal, "deploy", request.component)
    version = resolve(component, request)
    check_resources("deploy", instance, version, request.resourceClasses)
    spec = {"action": "deploy", **{field: version["spec"][field] for field in ("version", "image", "digest")}}
    if version["spec"].get("commit"):
      spec["commit"] = version["spec"]["commit"]
    overrides = overrides_of(request.replicas, request.resourceClasses)
    if overrides:
      spec["overrides"] = overrides
    return write(env, instance, component, spec, principal)

  @routes.post("/workloads:apply")
  def apply(environment: str, request: ApplyRequest, principal: Principal = Depends(current_principal)):
    env, items = plan_of(environment, request, principal)
    applied = 0
    for item in items:
      item["revision"] = None
      if request.dryRun or item["action"] == "unchanged":
        continue
      try:
        item["revision"] = write(env, item["instance"], item["component"], item["spec"], principal)["revision"]
      except HTTPException as error:
        # Not transactional: what was written stays, and applying again converges.
        raise HTTPException(error.status_code, f"{error.detail}; {applied} applied before it, apply again to converge")
      applied += 1
    return {
      "environment": environment,
      "applied": not request.dryRun,
      "summary": {action: sum(1 for item in items if item["action"] == action) for action in ("add", "change", "remove", "unchanged")},
      "items": [{key: item[key] for key in ("instance", "component", "action", "from", "to", "revision")} for item in items],
    }

  @routes.delete("/workloads/{instance}", status_code=202)
  def remove(environment: str, instance: str, principal: Principal = Depends(current_principal)):
    env, component = authorize(environment, instance, principal, "remove")
    if not any(view["instance"] == instance for view in instances_of(environment)):
      raise HTTPException(404, f"workload '{instance}' not found in environment '{environment}'")
    check_unrouted(environment, instance, component, "remove")
    return write(env, instance, component, {"action": "remove"}, principal)

  @routes.get("/workloads")
  def list_instances(environment: str, principal: Principal = Depends(current_principal)):
    usable(environment, principal)
    return {"items": instances_of(environment)}

  @routes.get("/workloads/{instance}")
  def get(environment: str, instance: str, principal: Principal = Depends(current_principal)):
    usable(environment, principal)
    found = next((view for view in instances_of(environment) if view["instance"] == instance), None)
    if found is None:
      raise HTTPException(404, f"workload '{instance}' not found in environment '{environment}'")
    return found

  def route_target(environment: str, component: str, principal: Principal, act: str) -> dict:
    if not LABEL.fullmatch(component):
      raise HTTPException(422, f"'{component}' is not a component name")
    env = writable(environment, principal)
    check_owner(component, principal, act)
    return env

  def check_rules(environment: str, component: str, rules: list[RouteRule]) -> None:
    alive = {instance: revision["component"] for instance, revision in live(environment).items()}
    if alive.get(component) != component:
      raise HTTPException(409, f"route of '{component}': its main instance {component}@{environment} is not deployed (the route attaches to its Service)")
    seen = set()
    for index, rule in enumerate(rules):
      if rule.weights is not None and index != len(rules) - 1:
        raise HTTPException(422, f"route of '{component}': the weights rule must be the last one, and there is at most one")
      if rule.weights is not None and sum(rule.weights.values()) != 100:
        raise HTTPException(422, f"route of '{component}': the weights add up to {sum(rule.weights.values())}, not 100")
      key = match_of(rule.model_dump(exclude_none=True))
      if key is not None and key in seen:
        raise HTTPException(422, f"route of '{component}': two rules match on {key[0]} {key[1]}={key[2]}")
      seen.add(key)
      for target in ([rule.to] if rule.to else []) + sorted(rule.weights or {}):
        if not LABEL.fullmatch(target):
          raise HTTPException(422, f"'{target}' is not an instance name")
        if target not in alive:
          raise HTTPException(409, f"route of '{component}': no instance '{target}' in environment '{environment}'")
        if alive[target] != component:
          raise HTTPException(409, f"route of '{component}': {target}@{environment} runs component '{alive[target]}'")

  @routes.put("/workloads/routes/{component}")
  def put_route(environment: str, component: str, request: RouteRequest, principal: Principal = Depends(current_principal)):
    env = route_target(environment, component, principal, "route")
    check_rules(environment, component, request.rules)
    name = f"{environment}.{component}"
    spec = {"environment": environment, "component": component, "rules": [rule.model_dump(exclude_none=True) for rule in request.rules]}
    try:
      current = state.get(ROUTES, name)
    except NotFound:
      current = None
    entry = journal.record("create" if current is None else "update", ROUTE_KIND, name, spec, principal.actor)
    try:
      if current is None:
        written = state.create(ROUTES, {
          "apiVersion": f"{GROUP}/{VERSION}",
          "kind": ROUTE_KIND,
          "metadata": {
            "name": name,
            "labels": {ENVIRONMENT_LABEL: environment, COMPONENT_LABEL: component},
            "ownerReferences": [{"apiVersion": f"{GROUP}/{VERSION}", "kind": "Environment", "name": environment, "uid": env["metadata"]["uid"]}],
          },
          "spec": spec,
        })
      else:
        # The whole object as read, finalizers included: only the spec changes.
        written = state.replace(ROUTES, {**current, "spec": spec})
    except (AlreadyExists, Conflict, NotFound):
      raise HTTPException(409, f"route of '{component}' in '{environment}' changed while writing: try again")
    journal.mark_applied(entry)
    return route_view(written)

  @routes.get("/workloads/routes/{component}")
  def get_route(environment: str, component: str, principal: Principal = Depends(current_principal)):
    usable(environment, principal)
    try:
      return route_view(state.get(ROUTES, f"{environment}.{component}"))
    except NotFound:
      raise HTTPException(404, f"no route of '{component}' in environment '{environment}'")

  @routes.delete("/workloads/routes/{component}", status_code=202)
  def delete_route(environment: str, component: str, principal: Principal = Depends(current_principal)):
    route_target(environment, component, principal, "route")
    name = f"{environment}.{component}"
    try:
      obj = state.get(ROUTES, name)
    except NotFound:
      raise HTTPException(404, f"no route of '{component}' in environment '{environment}'")
    entry = journal.record("delete", ROUTE_KIND, name, None, principal.actor)
    try:
      state.delete(ROUTES, name, uid=obj["metadata"].get("uid"))
    except NotFound:
      raise HTTPException(404, f"no route of '{component}' in environment '{environment}'")
    except Conflict:
      raise HTTPException(409, f"route of '{component}' in '{environment}' changed while deleting: try again")
    journal.mark_applied(entry)
    return {"name": name, "status": "deleting"}

  @routes.get("/revisions")
  def history(environment: str, instance: str | None = None, component: str | None = None, principal: Principal = Depends(current_principal)):
    usable(environment, principal)
    return {"items": [revision_view(obj) for obj in revisions_of(environment, instance, component)]}

  return routes
