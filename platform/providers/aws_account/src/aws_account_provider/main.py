import argparse
import logging
import time

from botocore.exceptions import BotoCoreError, ClientError

from .reconciler import Reconciler
from .store import CloudAccountStore
from .sts import Sts

log = logging.getLogger("aws-account-provider")


def publish_base(store, sts) -> bool:
  """The base identity, checked on every pass: an expired credential takes the capability down."""
  try:
    identity = sts.caller_identity()
  except (ClientError, BotoCoreError) as error:
    log.error("base credential unusable, cloud accounts are not verified: %s", error)
    store.clear_base_identity()
    return False
  store.publish_base_identity(identity["Arn"], identity["Account"])
  return True


def run(store, sts, reconciler: Reconciler, resync_seconds: int) -> None:
  """List, reconcile what is due, then watch until the resync timeout and start over."""
  while True:
    try:
      if not publish_base(store, sts):
        time.sleep(resync_seconds)
        continue
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
  parser = argparse.ArgumentParser(prog="aws-account-provider", description="Verify the trust of each AWS CloudAccount from the platform base credential.")
  parser.add_argument("--namespace", default="platform-system")
  parser.add_argument("--context", default=None, help="kubeconfig context, only when running outside the cluster")
  parser.add_argument("--resync-seconds", type=int, default=30)
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
  logging.getLogger("kubernetes").setLevel(logging.WARNING)
  store = CloudAccountStore(args.namespace, args.context)
  sts = Sts()
  log.info("watching cloud accounts in %s", args.namespace)
  run(store, sts, Reconciler(store, sts), args.resync_seconds)


if __name__ == "__main__":
  main()
