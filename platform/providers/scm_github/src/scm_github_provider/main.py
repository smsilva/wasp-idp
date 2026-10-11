import argparse
import logging
import time

from .reconciler import Reconciler
from .store import ConnectionStore, CredentialSecrets

log = logging.getLogger("scm-github-provider")


def run(store, reconciler: Reconciler, resync_seconds: int) -> None:
  """List, reconcile what is due, then watch until the resync timeout and start over.

  The periodic pass drives the backoff while a connection is not Ready and the 6 h revalidation.
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
  parser = argparse.ArgumentParser(prog="scm-github-provider", description="Validate each GitHub ScmConnection against its App installation.")
  parser.add_argument("--namespace", default="platform-system")
  parser.add_argument("--context", default=None, help="kubeconfig context, only when running outside the cluster")
  parser.add_argument("--resync-seconds", type=int, default=15)
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
  logging.getLogger("kubernetes").setLevel(logging.WARNING)
  logging.getLogger("httpx").setLevel(logging.WARNING)
  store = ConnectionStore(args.namespace, args.context)
  reconciler = Reconciler(store, CredentialSecrets(args.namespace))
  log.info("watching scm connections in %s", args.namespace)
  run(store, reconciler, args.resync_seconds)


if __name__ == "__main__":
  main()
