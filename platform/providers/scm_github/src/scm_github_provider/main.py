import argparse
import logging
import threading
import time
from pathlib import Path

from .build import RESOURCE_TYPES, BuildReconciler
from .component_creation import CreationReconciler
from .reconciler import Reconciler
from .store import CATALOG_GROUP, CredentialSecrets, ObjectStore, load_config

log = logging.getLogger("scm-github-provider")


def run(store, reconciler: Reconciler, resync_seconds: int) -> None:
  """List, reconcile what is due, then watch until the resync timeout and start over.

  The periodic pass drives the backoff while a connection is not Ready and the 6 h revalidation, and
  retries the creations that failed.
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
  parser = argparse.ArgumentParser(prog="scm-github-provider", description="Validate each GitHub ScmConnection against its App installation, and run each ComponentCreation and each Build.")
  parser.add_argument("--namespace", default="platform-system")
  parser.add_argument("--context", default=None, help="kubeconfig context, only when running outside the cluster")
  parser.add_argument("--resync-seconds", type=int, default=15)
  parser.add_argument("--workdir", type=Path, default=Path("/work"), help="where the creations render their content (an emptyDir)")
  parser.add_argument("--resource-types", default=",".join(RESOURCE_TYPES), help="resource types an app-spec.yaml may declare, comma-separated")
  args = parser.parse_args(argv)

  logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
  logging.getLogger("kubernetes").setLevel(logging.WARNING)
  logging.getLogger("httpx").setLevel(logging.WARNING)
  load_config(args.context)
  secrets = CredentialSecrets(args.namespace)
  connections = ObjectStore(args.namespace)
  creations = ObjectStore(args.namespace, "componentcreations")
  components = ObjectStore(args.namespace, "components", CATALOG_GROUP)
  creator = CreationReconciler(creations, connections, components, secrets, args.workdir)
  builds = ObjectStore(args.namespace, "builds")
  builder = BuildReconciler(
    builds, connections,
    ObjectStore(args.namespace, "versions", CATALOG_GROUP),
    ObjectStore(args.namespace, "resources", CATALOG_GROUP),
    secrets,
    resource_types=[item.strip() for item in args.resource_types.split(",") if item.strip()],
  )
  # Three watches in one process: this provider is the only reader of the App key (ADR 0025).
  threading.Thread(target=run, args=(creations, creator, args.resync_seconds), name="creations", daemon=True).start()
  threading.Thread(target=run, args=(builds, builder, args.resync_seconds), name="builds", daemon=True).start()
  log.info("watching scm connections, component creations and builds in %s", args.namespace)
  run(connections, Reconciler(connections, secrets), args.resync_seconds)


if __name__ == "__main__":
  main()
