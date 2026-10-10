import argparse
import logging
import time

from .helm import Helm
from .reconciler import Reconciler
from .store import EnvironmentStore, KubeconfigSecrets

log = logging.getLogger("local-vcluster-provider")


def run(store, reconciler: Reconciler, resync_seconds: int) -> None:
  """List, reconcile everything, then watch until the resync timeout and start over.

  The periodic full pass applies expiresAt and picks up the kubeconfig Secret that a new vcluster
  writes a few seconds after its Helm release is installed.
  """
  while True:
    try:
      items, resource_version = store.list()
      for obj in items:
        reconciler.reconcile(obj)
      for event_type, obj in store.watch(resource_version, resync_seconds):
        if event_type not in ("ADDED", "MODIFIED"):
          continue
        current = store.get(obj["metadata"]["name"])
        if current:
          reconciler.reconcile(current)
    except Exception:  # 410 Gone, API unavailable: back off and relist
      log.exception("watch interrupted, relisting")
      time.sleep(5)


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(prog="local-vcluster-provider", description="Provision each Environment as a vcluster inside the control plane cluster.")
  parser.add_argument("--namespace", default="platform-system")
  parser.add_argument("--context", default=None, help="kubeconfig context, only when running outside the cluster")
  parser.add_argument("--resync-seconds", type=int, default=10)
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
  logging.getLogger("kubernetes").setLevel(logging.WARNING)
  store = EnvironmentStore(args.namespace, args.context)
  reconciler = Reconciler(store, Helm(), KubeconfigSecrets())
  log.info("watching environments in %s", args.namespace)
  run(store, reconciler, args.resync_seconds)


if __name__ == "__main__":
  main()
