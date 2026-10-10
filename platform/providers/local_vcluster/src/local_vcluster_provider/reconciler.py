import logging
from datetime import datetime, timezone

FINALIZER = "platform.wasp.silvios.me/local-vcluster"
RELEASE = "vcluster"
# Host ports published by the k3d load balancer of platform-local (platform init maps this range).
PORTS = range(7100, 7120)
SERVICE_SELECTOR = "app=vcluster"

log = logging.getLogger("local-vcluster-provider")


def namespace_name(environment: str) -> str:
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


class NoFreePort(Exception):
  pass


class Reconciler:
  """One vcluster (Helm release `vcluster`) per Environment, in namespace env-<name>.

  It runs inside platform-local and cannot write files on the host: the kubeconfig goes to
  status.kubeconfigData and the CLI writes it locally.
  """

  def __init__(self, store, helm, secrets, now=utcnow):
    self.store = store
    self.helm = helm
    self.secrets = secrets
    self.now = now

  def reconcile(self, obj: dict) -> None:
    name = obj["metadata"]["name"]
    try:
      self._reconcile(obj)
    except Exception as error:  # keep the loop alive; the condition tells the user what failed
      log.exception("reconcile %s failed", name)
      if not obj["metadata"].get("deletionTimestamp"):
        self.store.patch_status(name, {"conditions": [ready_condition("False", "ProvisioningFailed", str(error)[:500])]})

  def _free_port(self, obj: dict) -> int:
    port = (obj.get("status") or {}).get("port")
    if port:
      return port
    used = self.secrets.used_ports(SERVICE_SELECTOR)
    port = next((p for p in PORTS if p not in used), None)
    if port is None:
      raise NoFreePort(f"all {len(PORTS)} environment ports ({PORTS.start}-{PORTS.stop - 1}) are in use")
    return port

  def _reconcile(self, obj: dict) -> None:
    metadata = obj["metadata"]
    name = metadata["name"]
    namespace = namespace_name(name)
    finalizers = metadata.get("finalizers") or []

    if metadata.get("deletionTimestamp"):
      if FINALIZER in finalizers:
        log.info("deleting vcluster %s", namespace)
        self.helm.uninstall(RELEASE, namespace)
        self.store.delete_namespace(namespace)
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

    port = self._free_port(obj)
    if not self.helm.installed(RELEASE, namespace):
      log.info("creating vcluster %s on port %s", namespace, port)
      self.store.patch_status(name, {
        "port": port,
        "conditions": [ready_condition("False", "Provisioning", f"creating vcluster in namespace {namespace}")],
      })
      self.helm.install(RELEASE, namespace, port)

    kubeconfig = self.secrets.read(namespace, f"vc-{RELEASE}")
    if not kubeconfig:
      # The vcluster writes this Secret once its API server is up; the next resync picks it up.
      self.store.patch_status(name, {
        "port": port,
        "conditions": [ready_condition("False", "Provisioning", f"waiting for the vcluster API server in {namespace}")],
      })
      return

    ready = current_ready(obj)
    status = obj.get("status") or {}
    if ready and ready.get("status") == "True" and status.get("kubeconfigData") == kubeconfig:
      return
    self.store.patch_status(name, {
      "port": port,
      "kubeconfigData": kubeconfig,
      "conditions": [ready_condition("True", "ClusterReady", f"vcluster running in namespace {namespace}, API on 127.0.0.1:{port}")],
    })
    log.info("environment %s ready", name)
