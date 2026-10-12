import argparse
import logging
import time

from .reconciler import Reconciler
from .store import SERVER, Secrets, Store, Vclusters

log = logging.getLogger("forager")


def run(store: Store, reconciler: Reconciler, resync_seconds: int, poll_seconds: int) -> None:
  """A full pass, then watch the revisions until one is added or the timeout ends, and start over.

  The timeout is short while a revision is open or a request is still provisioning or being
  released, and the resync otherwise.
  """
  while True:
    try:
      revisions, resource_version = store.list_revisions()
      pending = reconciler.reconcile(revisions, store.list_requests(), store.list_policies())
      for event_type, _ in store.watch_revisions(resource_version, poll_seconds if pending else resync_seconds):
        if event_type == "ADDED":
          break
    except Exception:  # 410 Gone, API unavailable: back off and relist
      log.exception("pass interrupted, relisting")
      time.sleep(5)


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(prog="forager-provider", description="Resolve the resources of each WorkloadRevision into ResourceRequests and provision them.")
  parser.add_argument("--namespace", default="platform-system")
  parser.add_argument("--secrets-namespace", default="platform-resources", help="where the generated credentials are kept")
  parser.add_argument("--context", default=None, help="kubeconfig context, only when running outside the cluster")
  parser.add_argument("--vcluster-server", default=SERVER, help="address of a vcluster API server, with {name} (and {port}, the host port)")
  parser.add_argument("--resync-seconds", type=int, default=30)
  parser.add_argument("--poll-seconds", type=int, default=5)
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
  logging.getLogger("kubernetes").setLevel(logging.WARNING)
  store = Store(args.namespace, args.context)
  reconciler = Reconciler(store, Vclusters(args.vcluster_server), Secrets(args.secrets_namespace))
  log.info("resolving resources of workload revisions in %s", args.namespace)
  run(store, reconciler, args.resync_seconds, args.poll_seconds)


if __name__ == "__main__":
  main()
