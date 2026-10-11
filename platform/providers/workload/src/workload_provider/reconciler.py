"""Revisions in, Deployments and instances out (ADR 0033).

For each instance, only the newest revision counts: an older one still open is closed as Superseded.
An open revision is applied (server-side apply, idempotent) on every pass until its rollout ends, so
a restart of the provider loses nothing. Once a deploy succeeds, every pass refreshes the runtime
health of its instance.

A Score with resources waits (ResourcesPending) until the Forager has resolved every one of them for
this revision (ResourceRequest status.revision) and provisioned it (Ready): its outputs and secretRef
fill the placeholders. A resource without provider ends the revision as ResourcesNotSupported, a
change of mode as ResourceModeChanged, a provisioner failure as ResourcesFailed.
"""
import logging
from datetime import datetime, timezone

from .manifests import MANAGER, NAMESPACE, UnsupportedSpec, render

GROUP = "platform.wasp.silvios.me"
VERSION = "v1alpha1"
OPEN = "Unknown"

log = logging.getLogger("workload-provider")


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


def timestamp(now: datetime) -> str:
  return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def ready_of(obj: dict) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), None)


def is_open(revision: dict) -> bool:
  ready = ready_of(revision)
  return ready is None or ready.get("status") == OPEN


# Resolved=False reasons of a ResourceRequest, and how they end the revision.
RESOLVE_FAILURES = {"NoProviderForCapability": "ResourcesNotSupported", "ResourceModeChanged": "ResourceModeChanged"}


def condition_of(obj: dict, kind: str) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == kind), None)


def instance_name(revision: dict) -> str:
  return f"{revision['spec']['environment']}.{revision['spec']['instance']}"


def spec_action(revision: dict) -> str:
  return revision["spec"].get("action", "deploy")


def rollout(deployment: dict | None) -> tuple[str, str]:
  """Where a Deployment's rollout stands: done, failed or progressing, with a message."""
  if deployment is None:
    return "progressing", "waiting for the Deployment"
  spec, status = deployment.get("spec") or {}, deployment.get("status") or {}
  desired = spec.get("replicas", 1)
  if status.get("observedGeneration", 0) < deployment["metadata"].get("generation", 0):
    return "progressing", "waiting for the Deployment controller"
  progressing = next((c for c in status.get("conditions") or [] if c.get("type") == "Progressing"), {})
  if progressing.get("reason") == "ProgressDeadlineExceeded":
    return "failed", progressing.get("message") or "the rollout made no progress"
  updated, available, total = status.get("updatedReplicas", 0), status.get("availableReplicas", 0), status.get("replicas", 0)
  if updated >= desired and available >= desired and total <= desired:
    return "done", f"{available}/{desired} replicas available"
  return "progressing", f"rolling out: {available}/{desired} replicas available"


def health(deployment: dict | None) -> tuple[dict, dict]:
  """The instance's replicas and Ready condition (Available, Progressing, Degraded)."""
  if deployment is None:
    return {"desired": 0, "ready": 0}, {"status": "False", "reason": "Degraded", "message": "the Deployment is missing from the vcluster"}
  spec, status = deployment.get("spec") or {}, deployment.get("status") or {}
  desired, ready = spec.get("replicas", 1), status.get("readyReplicas", 0)
  replicas = {"desired": desired, "ready": ready}
  state, message = rollout(deployment)
  if state == "failed":
    return replicas, {"status": "False", "reason": "Degraded", "message": message}
  rolling = status.get("observedGeneration", 0) < deployment["metadata"].get("generation", 0) or status.get("updatedReplicas", 0) < desired or status.get("replicas", 0) > desired
  if rolling:
    return replicas, {"status": "False", "reason": "Progressing", "message": message}
  if ready >= desired:
    return replicas, {"status": "True", "reason": "Available", "message": f"{ready}/{desired} replicas ready"}
  # The rollout is over and pods went missing since: crash loop, eviction.
  return replicas, {"status": "False", "reason": "Degraded", "message": f"{ready}/{desired} replicas ready"}


class Reconciler:
  def __init__(self, store, vclusters, now=utcnow):
    self.store = store
    self.vclusters = vclusters
    self.now = now

  def reconcile(self, revisions: list[dict], instances: list[dict]) -> bool:
    """One pass over everything; True while some revision is still open (the caller polls faster)."""
    newest: dict[str, dict] = {}
    for revision in sorted(revisions, key=lambda obj: obj["spec"]["revision"]):
      previous = newest.get(instance_name(revision))
      if previous is not None and is_open(previous):
        self._close(previous, "False", "Superseded", f"revision {revision['spec']['revision']} is newer")
      newest[instance_name(revision)] = revision
    kept = {obj["metadata"]["name"]: obj for obj in instances}
    pending = False
    for name, revision in newest.items():
      try:
        if is_open(revision):
          pending |= self._apply(revision, kept.get(name))
        elif ready_of(revision).get("reason") == "Succeeded" and spec_action(revision) != "remove" and name in kept:
          self._refresh(revision, kept[name])
      except Exception:  # keep the loop alive; the next pass tries again
        log.exception("reconcile %s failed", revision["metadata"]["name"])
        pending = True
    return pending

  def _condition(self, status: str, reason: str, message: str) -> dict:
    return {"type": "Ready", "status": status, "reason": reason, "message": message[:500], "lastTransitionTime": timestamp(self.now())}

  def _open(self, revision: dict, reason: str, message: str) -> None:
    ready = ready_of(revision) or {}
    if (ready.get("status"), ready.get("reason"), ready.get("message")) == (OPEN, reason, message):
      return
    status = {"conditions": [self._condition(OPEN, reason, message)]}
    if not (revision.get("status") or {}).get("startedAt"):
      status["startedAt"] = timestamp(self.now())
    self.store.patch_revision_status(revision["metadata"]["name"], status)
    revision["status"] = {**(revision.get("status") or {}), **status}

  def _close(self, revision: dict, status: str, reason: str, message: str) -> None:
    log.info("revision %s: %s (%s)", revision["metadata"]["name"], reason, message)
    patch = {"conditions": [self._condition(status, reason, message)], "finishedAt": timestamp(self.now())}
    self.store.patch_revision_status(revision["metadata"]["name"], patch)
    revision["status"] = {**(revision.get("status") or {}), **patch}

  def _apply(self, revision: dict, instance: dict | None) -> bool:
    spec = revision["spec"]
    environment = self.store.get_environment(spec["environment"])
    if environment is None:  # being deleted: the owner reference takes the revisions with it
      return False
    ready = ready_of(environment) or {}
    if ready.get("status") != "True" or not (environment.get("status") or {}).get("kubeconfigData"):
      self._open(revision, "EnvironmentNotReady", f"environment {spec['environment']} is not ready yet")
      return True
    if spec_action(revision) == "remove":
      return self._remove(revision, environment)
    version = self.store.get_version(f"{spec['component']}.{spec['version']}".lower())
    if version is None or (version.get("spec") or {}).get("appSpec") is None:
      self._close(revision, "False", "SpecNotIndexed", f"{spec['component']} {spec['version']} has no Workload Spec in the index")
      return False
    app_spec = version["spec"]["appSpec"]
    resources, summary = {}, []
    if app_spec.get("resources"):
      outcome, detail = self._resources(revision, sorted(app_spec["resources"]))
      if outcome == "pending":
        self._open(revision, "ResourcesPending", detail)
        return True
      if outcome != "ready":
        self._close(revision, "False", outcome, detail)
        return False
      resources, summary = detail
    try:
      objects, url = render(app_spec, revision, resources)
    except UnsupportedSpec as error:
      self._close(revision, "False", "UnsupportedSpec", str(error))
      return False
    vcluster = self.vclusters.of(environment)
    try:
      for obj in objects:
        vcluster.apply(obj, MANAGER)
    except Exception as error:
      self._close(revision, "False", "ApplyFailed", f"applying in the vcluster of {spec['environment']}: {error}")
      return False
    deployment = vcluster.deployment(NAMESPACE, spec["instance"])
    state, message = rollout(deployment)
    if state == "progressing":
      self._open(revision, "Pending", message)
      return True
    if state == "failed":
      self._close(revision, "False", "RolloutFailed", message)
      self._write_instance(revision, instance, deployment, url, summary)
      return False
    self._close(revision, "True", "Succeeded", message)
    self._write_instance(revision, instance, deployment, url, summary)
    return False

  def _resources(self, revision: dict, names: list[str]):
    """("ready", (resources, summary)), ("pending", message) or (closing reason, message)."""
    spec = revision["spec"]
    number = spec["revision"]
    resources, summary, waiting = {}, [], []
    for name in names:
      request = self.store.get_resource_request(f"{spec['environment']}.{spec['instance']}.{name}")
      if request is None or ((request.get("status") or {}).get("revision") or 0) < number:
        waiting.append(f"{name}: waiting for the Forager")
        continue
      resolved = condition_of(request, "Resolved") or {}
      if resolved.get("status") == "False":
        return RESOLVE_FAILURES.get(resolved.get("reason"), "ResourcesNotSupported"), resolved.get("message") or name
      ready = condition_of(request, "Ready") or {}
      if ready.get("status") == "False":
        return "ResourcesFailed", f"{name}: {ready.get('message') or ready.get('reason')}"
      if ready.get("status") != "True":
        waiting.append(f"{name}: {ready.get('message') or 'provisioning'}")
        continue
      status = request["status"]
      resources[name] = {"outputs": status.get("outputs") or {}, "secretRef": status.get("secretRef")}
      summary.append({"name": name, "type": request["spec"]["type"], "mode": request["spec"].get("mode"), "status": ready.get("reason")})
    if waiting:
      return "pending", "; ".join(waiting)
    return "ready", (resources, summary)

  def _remove(self, revision: dict, environment: dict) -> bool:
    """Deployment and Service out of the vcluster, then the instance; the revisions stay."""
    spec = revision["spec"]
    vcluster = self.vclusters.of(environment)
    try:
      vcluster.delete("v1", "Service", NAMESPACE, spec["instance"])
      vcluster.delete("apps/v1", "Deployment", NAMESPACE, spec["instance"])
    except Exception as error:
      self._close(revision, "False", "ApplyFailed", f"removing from the vcluster of {spec['environment']}: {error}")
      return False
    # The Forager's finalizer undoes each resource.
    self.store.delete_resource_requests(spec["environment"], spec["instance"])
    self.store.delete_instance(instance_name(revision))
    self._close(revision, "True", "Succeeded", f"removed from {spec['environment']}")
    return False

  def _write_instance(self, revision: dict, instance: dict | None, deployment: dict | None, url: str | None, resources: list[dict]) -> None:
    spec = revision["spec"]
    name = instance_name(revision)
    if instance is None:
      environment = self.store.get_environment(spec["environment"])
      self.store.create_instance({
        "apiVersion": f"{GROUP}/{VERSION}",
        "kind": "WorkloadInstance",
        "metadata": {
          "name": name,
          "labels": {f"{GROUP}/environment": spec["environment"], f"{GROUP}/component": spec["component"], f"{GROUP}/instance": spec["instance"]},
          "ownerReferences": [{"apiVersion": f"{GROUP}/{VERSION}", "kind": "Environment", "name": spec["environment"], "uid": environment["metadata"]["uid"]}],
        },
        "spec": {"environment": spec["environment"], "instance": spec["instance"], "component": spec["component"]},
      })
    replicas, condition = health(deployment)
    self.store.patch_instance_status(name, {
      "revision": spec["revision"],
      "version": spec["version"],
      "image": f"{spec['image']}@{spec['digest']}",
      "replicas": replicas,
      "url": url,
      "resources": resources,
      "conditions": [self._condition(**condition)],
    })

  def _refresh(self, revision: dict, instance: dict) -> None:
    environment = self.store.get_environment(revision["spec"]["environment"])
    if environment is None or not (environment.get("status") or {}).get("kubeconfigData"):
      return
    deployment = self.vclusters.of(environment).deployment(NAMESPACE, revision["spec"]["instance"])
    replicas, condition = health(deployment)
    status = instance.get("status") or {}
    current = ready_of(instance) or {}
    if status.get("replicas") == replicas and (current.get("status"), current.get("reason"), current.get("message")) == (condition["status"], condition["reason"], condition["message"]):
      return
    log.info("instance %s: %s (%s)", instance["metadata"]["name"], condition["reason"], condition["message"])
    self.store.patch_instance_status(instance["metadata"]["name"], {"replicas": replicas, "conditions": [self._condition(**condition)]})
