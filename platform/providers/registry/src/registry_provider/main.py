import argparse
import logging
import signal
import sys
import time

import httpx

from .reconciler import Reconciler
from .store import RegistryStore

log = logging.getLogger("registry-provider")


def run(store, reconciler: Reconciler, resync_seconds: int) -> None:
  """List and check every registry, then watch until the resync timeout and start over: a registry
  that stops answering shows within one resync."""
  while True:
    try:
      items, resource_version = store.list()
      for obj in items:
        reconciler.reconcile(obj)
      for event_type, obj in store.watch(resource_version, resync_seconds):
        if event_type == "ADDED":
          reconciler.reconcile(obj)
    except Exception:  # 410 Gone, API unavailable: back off and relist
      log.exception("watch interrupted, relisting")
      time.sleep(5)


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(prog="registry-provider", description="Check that each OCIRegistry answers the OCI Distribution API.")
  parser.add_argument("--namespace", default="platform-system")
  parser.add_argument("--context", default=None, help="kubeconfig context, only when running outside the cluster")
  parser.add_argument("--resync-seconds", type=int, default=300)
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
  # PID 1 in the pod: without a handler the kernel drops SIGTERM, and every rollout waits the 30 s grace period.
  signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
  logging.getLogger("kubernetes").setLevel(logging.WARNING)
  logging.getLogger("httpx").setLevel(logging.WARNING)
  store = RegistryStore(args.namespace, args.context)
  reconciler = Reconciler(store, httpx.Client())
  log.info("checking OCI registries in %s every %ss", args.namespace, args.resync_seconds)
  run(store, reconciler, args.resync_seconds)


if __name__ == "__main__":
  main()
