import argparse
import logging
import signal
import sys
import time

from .reconciler import Reconciler
from .store import CrossplaneStore, EnvironmentStore, load

log = logging.getLogger("crossplane-aws-provider")


def run(store, reconciler: Reconciler, resync_seconds: int) -> None:
  """List the accounts and environments, reconcile them, then watch environments until the resync timeout.

  The full pass picks up what Crossplane changed on the VPCs (it is not watched) and new accounts.
  """
  while True:
    try:
      accounts = store.accounts()
      reconciler.sync_accounts(accounts)
      by_name = {account["metadata"]["name"]: account for account in accounts}
      items, resource_version = store.list()
      for obj in items:
        reconciler.reconcile(obj, by_name)
      for event_type, obj in store.watch(resource_version, resync_seconds):
        if event_type not in ("ADDED", "MODIFIED"):
          continue
        current = store.get(obj["metadata"]["name"])
        if current:
          reconciler.reconcile(current, by_name)
    except Exception:  # 410 Gone, API unavailable: back off and relist
      log.exception("watch interrupted, relisting")
      time.sleep(5)


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(prog="crossplane-aws-provider", description="Provision each Environment in an AWS CloudAccount through Crossplane.")
  parser.add_argument("--namespace", default="platform-system")
  parser.add_argument("--context", default=None, help="kubeconfig context, only when running outside the cluster")
  parser.add_argument("--resync-seconds", type=int, default=15)
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
  # PID 1 in the pod: without a handler the kernel drops SIGTERM, and every rollout waits the 30 s grace period.
  signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
  logging.getLogger("kubernetes").setLevel(logging.WARNING)
  load(args.context)
  store = EnvironmentStore(args.namespace)
  log.info("watching environments in cloud accounts in %s", args.namespace)
  run(store, Reconciler(store, CrossplaneStore()), args.resync_seconds)


if __name__ == "__main__":
  main()
