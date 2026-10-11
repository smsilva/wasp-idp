"""Revisions in, ResourceRequests out (ADR 0022, 0031).

For the newest open deploy (or rollback) revision of each instance, every resource of its Score is
resolved against the BindingPolicies and gets a ResourceRequest <environment>.<instance>.<resource>,
created or reused, with status.revision set to that revision. Only when every resource of the
revision resolved are they provisioned: a revision that will fail never brings up a database nobody
uses. The workload provider waits for them and is the only writer of the revision status.
"""
import logging
from datetime import datetime, timezone

from .policy import resolve
from .postgres import PROVISIONERS, InvalidName

GROUP = "platform.wasp.silvios.me"
CATALOG_GROUP = f"catalog.{GROUP}"
VERSION = "v1alpha1"
FINALIZER = f"{GROUP}/forager"
OPEN = "Unknown"

log = logging.getLogger("forager")


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


def timestamp(now: datetime) -> str:
  return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def condition_of(obj: dict, kind: str) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == kind), None)


def is_open(revision: dict) -> bool:
  ready = condition_of(revision, "Ready")
  return ready is None or ready.get("status") == OPEN


def environment_ready(environment: dict | None) -> bool:
  if environment is None or environment["metadata"].get("deletionTimestamp"):
    return False
  ready = condition_of(environment, "Ready") or {}
  return ready.get("status") == "True" and bool((environment.get("status") or {}).get("kubeconfigData"))


def requested_class(revision: dict, name: str, resource: dict) -> str | None:
  override = (((revision["spec"].get("overrides") or {}).get("resources") or {}).get(name) or {}).get("class")
  return override or resource.get("class")


def _same(old: dict | None, new: dict) -> bool:
  return old is not None and all(old.get(key) == new.get(key) for key in ("type", "status", "reason", "message", "revision"))


class Reconciler:
  def __init__(self, store, vclusters, secrets, provisioners=PROVISIONERS, now=utcnow):
    self.store = store
    self.vclusters = vclusters
    self.secrets = secrets
    self.provisioners = provisioners
    self.now = now

  def reconcile(self, revisions: list[dict], requests: list[dict], policies: list[dict]) -> bool:
    """One pass; True while something is still moving (the caller polls faster)."""
    newest: dict[str, dict] = {}
    for revision in sorted(revisions, key=lambda obj: obj["spec"]["revision"]):
      newest[f"{revision['spec']['environment']}.{revision['spec']['instance']}"] = revision
    by_name = {obj["metadata"]["name"]: obj for obj in requests}
    pending = False
    for revision in newest.values():
      if not is_open(revision) or revision["spec"].get("action", "deploy") == "remove":
        continue
      pending = True  # the workload provider is waiting on this revision
      try:
        self._resolve(revision, by_name, policies)
      except Exception:  # keep the loop alive; the next pass tries again
        log.exception("resolve %s failed", revision["metadata"]["name"])
    for request in by_name.values():
      try:
        if request["metadata"].get("deletionTimestamp"):
          pending |= self._finalize(request)
        elif (condition_of(request, "Ready") or {}).get("reason") == "Provisioning":
          pending |= self._provision(request)
      except Exception:
        log.exception("request %s failed", request["metadata"]["name"])
        pending = True
    return pending

  def _condition(self, kind: str, status: str, reason: str, message: str, revision: int | None = None) -> dict:
    condition = {"type": kind, "status": status, "reason": reason, "message": message[:500], "lastTransitionTime": timestamp(self.now())}
    if revision is not None:
      condition["revision"] = revision
    return condition

  def _resolve(self, revision: dict, by_name: dict[str, dict], policies: list[dict]) -> None:
    spec = revision["spec"]
    environment = self.store.get_environment(spec["environment"])
    if environment is None or environment["metadata"].get("deletionTimestamp"):
      return
    version = self.store.get_version(f"{spec['component']}.{spec['version']}".lower())
    app_spec = ((version or {}).get("spec") or {}).get("appSpec")
    if not app_spec or not app_spec.get("resources"):
      return  # SpecNotIndexed or nothing to provision: the workload provider decides
    number = spec["revision"]
    plans = []
    for name, resource in sorted(app_spec["resources"].items()):
      kind, klass, resource_id = resource.get("type"), requested_class(revision, name, resource), resource.get("id")
      request_name = f"{spec['environment']}.{spec['instance']}.{name}"
      existing = by_name.get(request_name)
      item = resolve(policies, spec["environment"], kind, klass, resource_id)
      provisioner = f"{kind}/{item['mode']}" if item else None
      wanted = f" class {klass}" if klass else ""
      if item is None:
        resolved = ("False", "NoProviderForCapability", f"{name}: no provisioner for {kind}{wanted} in {spec['environment']}")
      elif provisioner not in self.provisioners:
        resolved = ("False", "NoProviderForCapability", f"{name}: the platform has no provider for {provisioner}")
      elif existing and existing["spec"].get("mode") and (existing["spec"]["mode"], existing["spec"].get("provisioner")) != (item["mode"], provisioner):
        resolved = ("False", "ResourceModeChanged", f"{name} is {existing['spec']['mode']} and the policy now resolves it as {item['mode']}: remove the workload and deploy again to change it")
      else:
        resolved = ("True", "Resolved", f"{name}: {provisioner}")
      plans.append((request_name, name, kind, klass, resource_id, item if resolved[0] == "True" else None, resolved))
    complete = all(plan[-1][0] == "True" for plan in plans)
    for request_name, name, kind, klass, resource_id, item, resolved in plans:
      request = by_name.get(request_name)
      if request is None:
        request = self._create(revision, environment, request_name, name, kind, klass, resource_id, item)
        by_name[request_name] = request
        if not resource_id:
          self._derive(spec["component"], name, kind)
      elif item and not request["spec"].get("mode"):
        fields = {"mode": item["mode"], "provisioner": f"{kind}/{item['mode']}", "params": item.get("params") or {}}
        self.store.patch_request(request_name, {"spec": fields})
        request["spec"].update(fields)
      self._status(request, number, resolved, complete)

  def _create(self, revision: dict, environment: dict, request_name: str, name: str, kind: str, klass: str | None, resource_id: str | None, item: dict | None) -> dict:
    spec = revision["spec"]
    body_spec = {"environment": spec["environment"], "instance": spec["instance"], "component": spec["component"], "resource": name, "type": kind}
    if klass:
      body_spec["class"] = klass
    if resource_id:
      body_spec["id"] = resource_id
    if item:
      body_spec.update({"mode": item["mode"], "provisioner": f"{kind}/{item['mode']}", "params": item.get("params") or {}})
    body = {
      "apiVersion": f"{GROUP}/{VERSION}",
      "kind": "ResourceRequest",
      "metadata": {
        "name": request_name,
        "labels": {f"{GROUP}/environment": spec["environment"], f"{GROUP}/instance": spec["instance"], f"{GROUP}/component": spec["component"]},
        "finalizers": [FINALIZER],
        "ownerReferences": [{"apiVersion": f"{GROUP}/{VERSION}", "kind": "Environment", "name": spec["environment"], "uid": environment["metadata"]["uid"]}],
      },
      "spec": body_spec,
    }
    log.info("request %s: created (%s)", request_name, body_spec.get("provisioner") or "unresolved")
    return self.store.create_request(body)

  def _derive(self, component: str, name: str, kind: str) -> None:
    """The catalog Resource of a resource without id (ADR 0023), never deleted here."""
    owner = self.store.get_component(component)
    if owner is None:
      return
    self.store.create_catalog_resource({
      "apiVersion": f"{CATALOG_GROUP}/{VERSION}",
      "kind": "Resource",
      "metadata": {"name": f"{component}-{name}", "annotations": {f"{GROUP}/created-by": "forager"}},
      "spec": {"owner": owner["spec"]["owner"], "system": owner["spec"]["system"], "type": kind, "description": f"{name} of {component}, derived from its Score"},
    })

  def _status(self, request: dict, number: int, resolved: tuple[str, str, str], complete: bool) -> None:
    status, reason, message = resolved
    resolved_condition = self._condition("Resolved", status, reason, message, number)
    ready = condition_of(request, "Ready")
    if ready and ready.get("status") == "True":
      ready_condition = ready
    elif complete:
      ready_condition = ready if ready and ready.get("reason") == "Provisioning" else self._condition("Ready", OPEN, "Provisioning", "provisioning")
    else:
      ready_condition = self._condition("Ready", OPEN, "Waiting", f"waiting for the other resources of revision {number}")
    current = request.get("status") or {}
    if current.get("revision") == number and _same(condition_of(request, "Resolved"), resolved_condition) and _same(ready, ready_condition):
      return
    patch = {"revision": number, "conditions": [resolved_condition, ready_condition]}
    self.store.patch_request_status(request["metadata"]["name"], patch)
    request["status"] = {**current, **patch}

  def _provision(self, request: dict) -> bool:
    spec = request["spec"]
    environment = self.store.get_environment(spec["environment"])
    if not environment_ready(environment):
      return True
    provisioner = self.provisioners[spec["provisioner"]]
    try:
      state, message, outputs, secret_ref = provisioner.ensure(request, spec.get("params") or {}, self.vclusters.of(environment), self.secrets)
    except InvalidName as error:
      state, message, outputs, secret_ref = "Failed", str(error), {}, None
    ready = {"Ready": ("True", "Ready"), "Failed": ("False", "Failed")}.get(state, (OPEN, "Provisioning"))
    ready_condition = self._condition("Ready", ready[0], ready[1], message)
    if _same(condition_of(request, "Ready"), ready_condition) and (request.get("status") or {}).get("outputs") == outputs:
      return state == "Provisioning"
    log.info("request %s: %s (%s)", request["metadata"]["name"], ready[1], message)
    conditions = [c for c in (request.get("status") or {}).get("conditions", []) if c.get("type") != "Ready"] + [ready_condition]
    patch = {"outputs": outputs, "secretRef": secret_ref, "conditions": conditions}
    self.store.patch_request_status(request["metadata"]["name"], patch)
    request["status"] = {**(request.get("status") or {}), **patch}
    return state == "Provisioning"

  def _finalize(self, request: dict) -> bool:
    finalizers = request["metadata"].get("finalizers") or []
    if FINALIZER not in finalizers:
      return False
    spec = request["spec"]
    environment = self.store.get_environment(spec["environment"])
    provisioner = self.provisioners.get(spec.get("provisioner") or "")
    # With the environment going away, the vcluster goes with it: only the control plane is left.
    if provisioner is not None and environment_ready(environment):
      provisioner.delete(request, self.vclusters.of(environment), self.secrets)
    else:
      self.secrets.delete(request["metadata"]["name"])
    self.store.patch_request(request["metadata"]["name"], {"metadata": {"finalizers": [f for f in finalizers if f != FINALIZER]}})
    log.info("request %s: released", request["metadata"]["name"])
    return False
