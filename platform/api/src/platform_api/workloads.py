"""Workload Instances (#292, ADR 0033): a version from the index deployed in an Environment.

The API writes only WorkloadRevisions, named <environment>.<instance>.<n>: the number is the newest
plus one, so two concurrent requests collide on the name and the second gets a 409 (optimistic
concurrency, no lock). The workload provider applies the newest revision in the vcluster and keeps
the WorkloadInstance, the runtime view. Writing needs can_use on the environment and the component's
owner team (or platform-admins); reading needs can_use. In phase 1 the instance name is the component
name, so a second instance of the same component cannot be asked for. A rollback is a new revision
with the version and overrides of an earlier one; a remove is a revision too, and the history stays
until the environment goes.

apply (#293) takes the plan of an environment (the helmfile of its instances) and diffs it against the
newest revision of each instance: one revision per instance that changes, and with prune a remove for
each instance the plan leaves out. Every instance is authorized and resolved before the first write.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import Principal, current_principal
from .builds import COMPONENTS, VERSION_PATTERN, VERSIONS
from .catalog import LABEL
from .environments import ADMIN_GROUP, can_use
from .journal import Journal
from .state import ENVIRONMENTS, GROUP, VERSION, AlreadyExists, NotFound

REVISIONS = "workloadrevisions"
INSTANCES = "workloadinstances"
KIND = "WorkloadRevision"
ENVIRONMENT_LABEL = f"{GROUP}/environment"
COMPONENT_LABEL = f"{GROUP}/component"
INSTANCE_LABEL = f"{GROUP}/instance"
# Ready=Unknown: the provider has not closed the revision yet.
OPEN = "Unknown"
MAX_PLAN = 100
# Without the override the provider runs one replica.
DEFAULT_REPLICAS = 1


class RevisionRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  version: str | None = None
  branch: str | None = None
  replicas: int | None = Field(default=None, ge=0, le=20)
  # A rollback copies the version and the overrides of that revision of the same instance.
  rollbackTo: int | None = Field(default=None, ge=1)

  @field_validator("version")
  @classmethod
  def check_version(cls, value: str | None) -> str | None:
    if value is not None and not VERSION_PATTERN.fullmatch(value):
      raise ValueError("<major>.<minor>.<patch>[-<pre-release>], e.g. 1.0.0-rc.1")
    return value


class PlanEntry(BaseModel):
  model_config = ConfigDict(extra="forbid")

  # Phase 1: the instance is named after its component, so only the key itself is accepted (#294).
  component: str | None = None
  version: str | None = None
  branch: str | None = None
  replicas: int | None = Field(default=None, ge=0, le=20)

  check_version = field_validator("version")(RevisionRequest.check_version.__func__)


class ApplyRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  workloads: dict[str, PlanEntry] = Field(max_length=MAX_PLAN)
  dryRun: bool = True
  prune: bool = False


def ready_of(obj: dict) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), None)


def is_open(revision: dict) -> bool:
  ready = ready_of(revision)
  return ready is None or ready.get("status") == OPEN


def revision_view(obj: dict) -> dict:
  spec = obj.get("spec", {})
  status = obj.get("status") or {}
  ready = ready_of(obj)
  return {
    "kind": KIND,
    "name": obj["metadata"]["name"],
    **{field: spec.get(field) for field in ("environment", "instance", "component", "revision", "action", "version", "image", "digest", "commit", "requestedBy", "rollbackOf")},
    "replicas": (spec.get("overrides") or {}).get("replicas"),
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

  def revisions_of(environment: str, instance: str | None = None) -> list[dict]:
    items = [obj for obj in state.list(REVISIONS) if obj["spec"].get("environment") == environment and (instance is None or obj["spec"].get("instance") == instance)]
    return sorted(items, key=lambda obj: (obj["spec"]["instance"], obj["spec"]["revision"]))

  def instances_of(environment: str) -> list[dict]:
    """One view per instance: those the provider keeps, and those whose first revision is still open.
    A closed revision with no instance behind it (a failed first deploy, a remove) shows nothing."""
    latest: dict[str, dict] = {}
    for obj in revisions_of(environment):
      latest[obj["spec"]["instance"]] = obj
    kept = {obj["spec"]["instance"]: obj for obj in state.list(INSTANCES) if obj["spec"].get("environment") == environment}
    views = []
    for instance, revision in sorted(latest.items()):
      obj = kept.get(instance)
      if obj is None and not is_open(revision):
        continue
      views.append(instance_view(environment, instance, obj, revision))
    return views

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

  def authorize(environment: str, instance: str, principal: Principal, act: str) -> tuple[dict, str]:
    """The environment and the component, for a principal who may write revisions of the instance."""
    if not LABEL.fullmatch(instance):
      raise HTTPException(422, f"'{instance}' is not an instance name")
    env = usable(environment, principal)
    # Phase 1: the instance is named after its component.
    component = instance
    try:
      owner = (state.get(COMPONENTS, component).get("spec") or {}).get("owner")
    except NotFound:
      raise HTTPException(404, f"component '{component}' not found")
    if not (owner in principal.teams or ADMIN_GROUP in principal.groups):
      raise HTTPException(403, f"{act} of '{component}': only members of its owner team ({owner or 'none'}) and {ADMIN_GROUP} {act} it")
    return env, component

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

  def wanted(revision: dict) -> dict:
    return {"version": revision["version"], "replicas": DEFAULT_REPLICAS if revision["replicas"] is None else revision["replicas"]}

  def live(environment: str) -> dict[str, dict]:
    """The newest revision of each instance that runs or is on its way: a remove, or a failed first
    deploy, leaves nothing to diff against."""
    return {view["instance"]: view["latestRevision"] for view in instances_of(environment) if view["latestRevision"]["action"] != "remove"}

  def plan_of(environment: str, request: "ApplyRequest", principal: Principal) -> tuple[dict, list[dict]]:
    """The environment and one item per instance of the plan, and with prune per instance left out.
    Raises before anything is written when one cannot be applied."""
    env = usable(environment, principal)
    newest = live(environment)
    items = []
    for instance, entry in sorted(request.workloads.items()):
      if entry.component is not None and entry.component != instance:
        raise HTTPException(422, f"apply of '{instance}': component '{entry.component}' differs from the instance name; more than one instance of a component is #294")
      if (entry.version is None) == (entry.branch is None):
        raise HTTPException(422, f"apply of '{instance}': give either version or branch")
      _, component = authorize(environment, instance, principal, "deploy")
      version = resolve(component, RevisionRequest(version=entry.version, branch=entry.branch))
      to = {"version": version["spec"]["version"], "replicas": entry.replicas if entry.replicas is not None else DEFAULT_REPLICAS}
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
      if entry.replicas is not None:
        spec["overrides"] = {"replicas": entry.replicas}
      items.append({"instance": instance, "component": component, "action": action, "from": wanted(current) if current else None, "to": to, "spec": spec})
    if request.prune:
      for instance, current in sorted(newest.items()):
        if instance in request.workloads:
          continue
        _, component = authorize(environment, instance, principal, "remove")
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
      if request.version is not None or request.branch is not None or request.replicas is not None:
        raise HTTPException(422, f"rollback of '{instance}': rollbackTo takes the version and replicas of that revision, give nothing else")
      env, component = authorize(environment, instance, principal, "rollback")
      source = rollback_source(environment, instance, request.rollbackTo)["spec"]
      spec = {"action": "rollback", "rollbackOf": request.rollbackTo, **{field: source[field] for field in ("version", "image", "digest", "commit", "overrides") if field in source}}
      return write(env, instance, component, spec, principal)
    if (request.version is None) == (request.branch is None):
      raise HTTPException(422, f"deploy of '{instance}': give either version or branch")
    env, component = authorize(environment, instance, principal, "deploy")
    version = resolve(component, request)
    spec = {"action": "deploy", **{field: version["spec"][field] for field in ("version", "image", "digest")}}
    if version["spec"].get("commit"):
      spec["commit"] = version["spec"]["commit"]
    if request.replicas is not None:
      spec["overrides"] = {"replicas": request.replicas}
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

  @routes.get("/revisions")
  def history(environment: str, instance: str | None = None, principal: Principal = Depends(current_principal)):
    usable(environment, principal)
    return {"items": [revision_view(obj) for obj in revisions_of(environment, instance)]}

  return routes
