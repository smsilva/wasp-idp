import argparse
import logging
import time
from pathlib import Path

from .k3d import K3d
from .reconciler import Reconciler
from .store import EnvironmentStore

log = logging.getLogger("local-k3d-provider")


def run(store, reconciler: Reconciler, resync_seconds: int) -> None:
  """List, reconcile everything, then watch until the resync timeout and start over.

  The periodic full pass is what applies expiresAt: nothing changes on the object when it expires.
  """
  while True:
    try:
      items, resource_version = store.list()
      for obj in items:
        reconciler.reconcile(obj)
      for event_type, obj in store.watch(resource_version, resync_seconds):
        if event_type not in ("ADDED", "MODIFIED"):
          continue
        # Events queue up while a cluster is created; act on the current object, not a stale copy.
        current = store.get(obj["metadata"]["name"])
        if current:
          reconciler.reconcile(current)
    except Exception:  # 410 Gone, API unavailable: back off and relist
      log.exception("watch interrupted, relisting")
      time.sleep(5)


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(prog="local-k3d-provider", description="Provision each Environment as a local k3d cluster.")
  parser.add_argument("--context", default="k3d-platform-local", help="kubectl context of the control plane cluster")
  parser.add_argument("--namespace", default="platform-system")
  parser.add_argument("--kubeconfig-dir", default=str(Path.home() / ".config" / "platform" / "environments"))
  parser.add_argument("--resync-seconds", type=int, default=30)
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
  logging.getLogger("kubernetes").setLevel(logging.WARNING)
  store = EnvironmentStore(args.namespace, args.context)
  reconciler = Reconciler(store, K3d(), Path(args.kubeconfig_dir))
  log.info("watching environments in %s/%s", args.context, args.namespace)
  try:
    run(store, reconciler, args.resync_seconds)
  except KeyboardInterrupt:
    log.info("stopped")


if __name__ == "__main__":
  main()
