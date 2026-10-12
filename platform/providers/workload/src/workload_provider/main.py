import argparse
import logging
import signal
import sys
import threading
import time

from .reconciler import Reconciler
from .routes import RouteReconciler
from .store import REVISIONS, ROUTES, SERVER, Store, Vclusters

log = logging.getLogger("workload-provider")
# How long one watch request lasts before it is opened again.
WATCH_SECONDS = 300


def wakes(event_type: str, obj: dict, seen: dict[str, int]) -> bool:
  """Whether a watch event is a change of the desired state: a new object, a deleted one, one being
  deleted (its finalizer has work), a new generation. The status writes of this provider change no
  generation, so they never wake the loop that made them."""
  name = obj["metadata"]["name"]
  generation = obj["metadata"].get("generation")
  if event_type == "DELETED":
    seen.pop(name, None)
    return True
  if obj["metadata"].get("deletionTimestamp"):
    seen[name] = generation
    return True
  previous = seen.get(name)
  seen[name] = generation
  return event_type == "ADDED" or previous != generation


def watch(store: Store, plural: str, wake: threading.Event) -> None:
  """Sets wake on every change of the plural, forever: one thread per plural."""
  seen: dict[str, int] = {}
  while True:
    try:
      items, resource_version = store.list(plural)
      seen.update({obj["metadata"]["name"]: obj["metadata"].get("generation") for obj in items})
      for event_type, obj in store.watch(plural, resource_version, WATCH_SECONDS):
        if event_type in ("ADDED", "MODIFIED", "DELETED") and wakes(event_type, obj, seen):
          wake.set()
    except Exception:  # 410 Gone, API unavailable: back off and relist
      log.exception("watch of %s interrupted, relisting", plural)
      time.sleep(5)


def run(store: Store, reconciler: Reconciler, routes: RouteReconciler, resync_seconds: int, poll_seconds: int) -> None:
  """A full pass, then wait until a revision or a route changes (a route takes effect in about a
  second) or the timeout ends, and start over.

  The timeout is short while a revision or a route is pending (a rollout, the mesh accepting an
  HTTPRoute, followed by polling) and the resync otherwise, which refreshes the health of every
  instance.
  """
  wake = threading.Event()
  for plural in (REVISIONS, ROUTES):
    threading.Thread(target=watch, args=(store, plural, wake), name=f"watch-{plural}", daemon=True).start()
  while True:
    # Cleared before listing: a change made during the pass wakes the next one.
    wake.clear()
    pending = False
    try:
      pending |= reconciler.reconcile(store.list(REVISIONS)[0], store.list_instances())
      pending |= routes.reconcile(store.list(ROUTES)[0])
    except Exception:  # API unavailable: back off and relist
      log.exception("pass interrupted, relisting")
      time.sleep(5)
    wake.wait(poll_seconds if pending else resync_seconds)


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(prog="workload-provider", description="Apply each WorkloadRevision and WorkloadRoute in the vcluster of its Environment and keep the WorkloadInstance.")
  parser.add_argument("--namespace", default="platform-system")
  parser.add_argument("--context", default=None, help="kubeconfig context, only when running outside the cluster")
  parser.add_argument("--vcluster-server", default=SERVER, help="address of a vcluster API server, with {name} (and {port}, the host port)")
  parser.add_argument("--resync-seconds", type=int, default=30)
  parser.add_argument("--poll-seconds", type=int, default=5)
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(threadName)s %(message)s")
  # PID 1 in the pod: without a handler the kernel drops SIGTERM, and every rollout waits the 30 s grace period.
  signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
  logging.getLogger("kubernetes").setLevel(logging.WARNING)
  store = Store(args.namespace, args.context)
  vclusters = Vclusters(args.vcluster_server)
  log.info("watching workload revisions and routes in %s", args.namespace)
  run(store, Reconciler(store, vclusters), RouteReconciler(store, vclusters), args.resync_seconds, args.poll_seconds)


if __name__ == "__main__":
  main()
