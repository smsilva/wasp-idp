import logging
from datetime import datetime, timezone
from pathlib import Path

FINALIZER = "platform.wasp.silvios.me/local-k3d"

log = logging.getLogger("local-k3d-provider")


def cluster_name(environment: str) -> str:
  return f"env-{environment}"


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


def parse_time(value: str) -> datetime:
  return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ready_condition(status: str, reason: str, message: str) -> dict:
  return {
    "type": "Ready",
    "status": status,
    "reason": reason,
    "message": message,
    "lastTransitionTime": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
  }


def current_ready(obj: dict) -> dict | None:
  conditions = (obj.get("status") or {}).get("conditions", [])
  return next((c for c in conditions if c.get("type") == "Ready"), None)


class Reconciler:
  def __init__(self, store, k3d, kubeconfig_dir: Path, now=utcnow):
    self.store = store
    self.k3d = k3d
    self.kubeconfig_dir = kubeconfig_dir
    self.now = now

  def kubeconfig_path(self, name: str) -> Path:
    return self.kubeconfig_dir / f"{name}.kubeconfig"

  def reconcile(self, obj: dict) -> None:
    name = obj["metadata"]["name"]
    try:
      self._reconcile(obj)
    except Exception as error:  # keep the loop alive; the condition tells the user what failed
      log.exception("reconcile %s failed", name)
      if not obj["metadata"].get("deletionTimestamp"):
        self.store.patch_status(name, {"conditions": [ready_condition("False", "ProvisioningFailed", str(error)[:500])]})

  def _reconcile(self, obj: dict) -> None:
    metadata = obj["metadata"]
    name = metadata["name"]
    cluster = cluster_name(name)
    finalizers = metadata.get("finalizers") or []

    if metadata.get("deletionTimestamp"):
      if FINALIZER in finalizers:
        if self.k3d.exists(cluster):
          log.info("deleting cluster %s", cluster)
          self.k3d.delete(cluster)
        self.kubeconfig_path(name).unlink(missing_ok=True)
        self.store.set_finalizers(name, [f for f in finalizers if f != FINALIZER])
        log.info("environment %s removed", name)
      return

    expires_at = obj.get("spec", {}).get("expiresAt")
    if expires_at and parse_time(expires_at) <= self.now():
      log.info("environment %s expired at %s, deleting", name, expires_at)
      self.store.delete(name)
      return

    if FINALIZER not in finalizers:
      self.store.set_finalizers(name, [*finalizers, FINALIZER])

    kubeconfig = self.kubeconfig_path(name)
    if not self.k3d.exists(cluster):
      log.info("creating cluster %s", cluster)
      self.store.patch_status(name, {"conditions": [ready_condition("False", "Provisioning", f"creating k3d cluster {cluster}")]})
      self.k3d.create(cluster)
      self.k3d.write_kubeconfig(cluster, kubeconfig)
    elif not kubeconfig.exists():
      self.k3d.write_kubeconfig(cluster, kubeconfig)

    ready = current_ready(obj)
    status = obj.get("status") or {}
    if ready and ready.get("status") == "True" and status.get("kubeconfig") == str(kubeconfig):
      return
    self.store.patch_status(name, {
      "kubeconfig": str(kubeconfig),
      "conditions": [ready_condition("True", "ClusterReady", f"k3d cluster {cluster} is running")],
    })
    log.info("environment %s ready", name)

