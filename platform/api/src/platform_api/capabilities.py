"""The capabilities of the platform, computed (ADR 0034 §4, ADR 0039): which Deployments implement each one,
whether they run, and whether what operators configure is there. platform-admins see the drivers and the
detail; everyone else, the name and the status."""
from fastapi import APIRouter, Depends, HTTPException, Request

from . import cloud_accounts, registries, scm
from .auth import Principal, current_principal
from .environments import ADMIN_GROUP

GROUP = "platform.wasp.silvios.me"
# On each Deployment that implements a capability: the provider, the capabilities it serves (a label
# value takes no comma, so they are dot-separated) and, for a driver of a vendor-neutral subsystem, its vendor.
PROVIDER_LABEL = f"{GROUP}/provider"
CAPABILITIES_LABEL = f"{GROUP}/capabilities"
VENDOR_LABEL = f"{GROUP}/vendor"
# Set by `platform init` on the Keycloak Deployment: the identity providers of the realm, dot-separated.
IDENTITY_PROVIDERS_ANNOTATION = f"{GROUP}/identity-providers"

# The subsystem map of ADR 0034, in its order: name and depends_on.
SUBSYSTEMS = {
  "identity": [],
  "catalog": ["identity"],
  "environment": ["identity"],
  "scm": ["identity", "catalog"],
  "registry": ["identity"],
  "build": ["scm", "catalog", "registry"],
  "cloud-account": ["identity"],
  "resources": ["environment", "build", "catalog"],
  "workload": ["environment", "build", "resources", "registry"],
  "observability": ["environment"],
}

ACTIVE, NOT_CONFIGURED, DEGRADED, UNREACHABLE, NO_PROVIDER = "Active", "NotConfigured", "Degraded", "Unreachable", "NoProviderForCapability"
WRITES = {"POST", "PUT", "PATCH", "DELETE"}


class NoProvider(Exception):
  """A write to an optional subsystem no Deployment implements: 503, never a CRD nothing reconciles (ADR 0034 §4)."""

  def __init__(self, name: str):
    super().__init__(f"capability '{name}' has no provider installed: see platform status {name}")
    self.name = name


class KubeDeployments:
  """The Deployments that declare a capability, in the namespaces of the platform."""

  def __init__(self, namespaces: tuple[str, ...] = ("platform-system", "platform-auth")):
    from kubernetes import client

    self.apps = client.AppsV1Api()
    self.namespaces = namespaces
    self._api_exception = client.ApiException

  def list(self) -> list[dict]:
    found = []
    for namespace in self.namespaces:
      try:
        items = self.apps.list_namespaced_deployment(namespace, label_selector=CAPABILITIES_LABEL).items
      except self._api_exception:
        continue
      for item in items:
        found.append({
          "name": item.metadata.name,
          "namespace": item.metadata.namespace,
          "labels": item.metadata.labels or {},
          "annotations": item.metadata.annotations or {},
          "image": item.spec.template.spec.containers[0].image,
          "desired": item.spec.replicas if item.spec.replicas is not None else 1,
          "ready": item.status.ready_replicas or 0,
        })
    return found


def version(image: str) -> str:
  """The tag of an image: `platform init` tags each build with its image id (12 hex digits)."""
  name = image.split("@", 1)[0]
  tail = name.rsplit("/", 1)[-1]
  return tail.split(":", 1)[1] if ":" in tail else "latest"


def driver(deployment: dict) -> dict:
  labels = deployment["labels"]
  return {
    "provider": labels.get(PROVIDER_LABEL) or deployment["name"],
    "vendor": labels.get(VENDOR_LABEL),
    "deployment": f"{deployment['namespace']}/{deployment['name']}",
    "version": version(deployment["image"]),
    "replicas": {"desired": deployment["desired"], "ready": deployment["ready"]},
    "status": ACTIVE if deployment["ready"] > 0 else UNREACHABLE,
    "annotations": deployment["annotations"],
  }


def drivers_of(deployments: list[dict]) -> dict[str, list[dict]]:
  found = {name: [] for name in SUBSYSTEMS}
  for deployment in deployments:
    for name in deployment["labels"].get(CAPABILITIES_LABEL, "").split("."):
      if name in found:
        found[name].append(driver(deployment))
  for drivers in found.values():
    drivers.sort(key=lambda item: (item["vendor"] or "", item["provider"]))
  return found


def counted(states: list[str]) -> str:
  """'2 ready, 1 MissingPermissions': the ready ones first, then each other state."""
  tally = {}
  for state in states:
    tally[state] = tally.get(state, 0) + 1
  ready = tally.pop("ready", 0)
  return ", ".join([f"{ready} ready", *(f"{count} {state}" for state, count in sorted(tally.items()))])


def plural(count: int, word: str, many: str | None = None) -> str:
  return f"{count} {word if count == 1 else many or word + 's'}"


def identity(item: dict) -> None:
  providers = {
    name
    for found in item["drivers"]
    for name in (found["annotations"].get(IDENTITY_PROVIDERS_ANNOTATION) or "").split(".") if name
  }
  if "google" not in providers:
    # Not a failure: sign-in with a password works without it.
    item["detail"] = "without Google IdP"
    item["fix"] = "platform init with GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET set"


def scm_connections(item: dict, connections: list[dict]) -> None:
  views = sorted((scm.view(obj) for obj in connections), key=lambda view: view["name"])
  item["connections"] = [
    {key: view[key] for key in ("name", "vendor", "org", "default", "status", "message")} for view in views
  ]
  if not views:
    item["status"], item["detail"] = NOT_CONFIGURED, "no connection ready"
    item["fix"] = "platform scm connection add <name> --org <org>"
    return
  failing = [view for view in views if view["status"] != "ready"]
  if failing:
    item["status"] = DEGRADED
    item["detail"] = f"{plural(len(views), 'connection')}: {counted([view['status'] for view in views])}"
    item["fix"] = "; ".join(f"{view['name']}: platform scm connection get {view['name']}" for view in failing)
  elif len(views) == 1:
    view = views[0]
    item["detail"] = f"{view['name']}{' (default)' if view['default'] else ''}"
  else:
    item["detail"] = f"{plural(len(views), 'connection')} ready"


def oci_registries(item: dict, found: list[dict]) -> None:
  """Registries are platform-admins', like connections: one not ready, or no default, degrades the capability."""
  views = sorted((registries.view(obj) for obj in found), key=lambda view: view["name"])
  item["registries"] = [
    {key: view[key] for key in ("name", "vendor", "address", "default", "status", "message")} for view in views
  ]
  if not views:
    item["status"], item["detail"] = NOT_CONFIGURED, "no registry"
    item["fix"] = "platform registry add <name> --scm-connection <connection> --default"
    return
  failing = [view for view in views if view["status"] != "ready"]
  if failing:
    item["status"] = DEGRADED
    item["detail"] = f"{plural(len(views), 'registry', 'registries')}: {counted([view['status'] for view in views])}"
    item["fix"] = "; ".join(f"{view['name']}: platform registry get {view['name']}" for view in failing)
  elif not any(view["default"] for view in views):
    # A build without --registry is refused with NoDefaultRegistry.
    item["status"], item["detail"] = DEGRADED, "no default registry"
    item["fix"] = "platform registry set-default <name>"
  else:
    default = next(view for view in views if view["default"])
    item["detail"] = f"{default['name']} (default)" + (f", {plural(len(views) - 1, 'other')}" if len(views) > 1 else "")


def build(item: dict, needed: list[dict]) -> None:
  """A build runs through an scm connection and pushes to a registry: what holds those back holds back build."""
  waiting = [other for other in needed if other["status"] in (NOT_CONFIGURED, DEGRADED)]
  if not waiting:
    return
  item["status"] = DEGRADED if any(other["status"] == DEGRADED for other in waiting) else NOT_CONFIGURED
  parts = []
  for other in waiting:
    failing = [row["name"] for row in other.get("connections", other.get("registries", [])) if row["status"] != "ready"]
    parts.append(f"needs {other['name']}{': ' + ', '.join(failing) if failing else ''}")
  item["detail"] = "; ".join(parts)


def cloud(item: dict, base_arn: str | None, accounts: list[dict]) -> None:
  """The base identity of each driver is the platform's part; an account that is not ready is its owner's."""
  views = [cloud_accounts.view(obj) for obj in accounts]
  for found in item["drivers"]:
    found["baseIdentity"] = base_arn if found["vendor"] == "aws" else None
  # Counted by vendor, never named: a regular user does not see the accounts of others.
  item["accounts"] = []
  for vendor in sorted({view["vendor"] for view in views}):
    states = [view["status"] for view in views if view["vendor"] == vendor]
    not_ready = {}
    for state in states:
      if state != "ready":
        not_ready[state] = not_ready.get(state, 0) + 1
    item["accounts"].append({"vendor": vendor, "ready": states.count("ready"), "notReady": not_ready})
  configured = [found for found in item["drivers"] if found["baseIdentity"]]
  if not configured:
    item["status"], item["detail"] = NOT_CONFIGURED, "no base identity"
    item["fix"] = "platform init --aws-profile <profile>"
    return
  if len(configured) < len(item["drivers"]):
    missing = ", ".join(found["provider"] for found in item["drivers"] if not found["baseIdentity"])
    item["status"], item["detail"] = DEGRADED, f"no base identity: {missing}"
    return
  if views:
    item["detail"] = f"{plural(len(views), 'account')}: {counted([view['status'] for view in views])}"


def compute(deployments: list[dict], connections: list[dict], accounts: list[dict], base_arn: str | None, found_registries: list[dict] = ()) -> list[dict]:
  drivers = drivers_of(deployments)
  items = {}
  for name, depends_on in SUBSYSTEMS.items():
    item = {"name": name, "status": ACTIVE, "dependsOn": depends_on, "drivers": drivers[name], "detail": None, "fix": None}
    items[name] = item
    up = [found for found in item["drivers"] if found["status"] == ACTIVE]
    down = [found for found in item["drivers"] if found["status"] != ACTIVE]
    if not item["drivers"]:
      item["status"], item["detail"] = NO_PROVIDER, "not installed"
      continue
    if not up:
      item["status"] = UNREACHABLE
      item["detail"] = ", ".join(f"{found['provider']}: {found['replicas']['ready']}/{found['replicas']['desired']} replicas ready" for found in down)
      continue
    if name == "identity":
      identity(item)
    elif name == "scm":
      scm_connections(item, connections)
    elif name == "registry":
      oci_registries(item, list(found_registries))
    elif name == "build":
      build(item, [items["scm"], items["registry"]])
    elif name == cloud_accounts.CAPABILITY:
      cloud(item, base_arn, accounts)
    # A driver down next to one that works: the capability still serves, in part.
    if down and item["status"] == ACTIVE:
      item["status"] = DEGRADED
      item["detail"] = ", ".join(f"{found['provider']}: {found['replicas']['ready']}/{found['replicas']['desired']} replicas ready" for found in down)
  for item in items.values():
    item["providers"] = sorted({found["provider"] for found in item["drivers"]})
    for found in item["drivers"]:
      found.pop("annotations")
  return list(items.values())


def installed(deployments: list[dict], name: str) -> bool:
  return any(name in deployment["labels"].get(CAPABILITIES_LABEL, "").split(".") for deployment in deployments)


def requires(deployments, name: str):
  """A router dependency: the writes of an optional subsystem need a provider; reads stay open.

  Without a Deployment reader (outside a cluster, and in most tests) there is nothing to check."""
  def check(request: Request) -> None:
    if deployments is None or request.method not in WRITES:
      return
    # A caller without a token gets 401 first, as on every other route: absence is not news for strangers.
    current_principal(request)
    if not installed(deployments.list(), name):
      raise NoProvider(name)

  return check


def visible(item: dict, principal: Principal) -> dict:
  if ADMIN_GROUP in principal.groups:
    return item
  return {"name": item["name"], "status": item["status"]}


def router(state, deployments, base_identity) -> APIRouter:
  routes = APIRouter(prefix="/v1/capabilities")

  def current() -> list[dict]:
    return compute(
      deployments.list() if deployments else [],
      state.list(scm.PLURAL),
      state.list(cloud_accounts.CLOUD_ACCOUNTS),
      base_identity.arn() if base_identity else None,
      state.list(registries.REGISTRIES),
    )

  @routes.get("")
  def list_capabilities(principal: Principal = Depends(current_principal)):
    return {"items": [visible(item, principal) for item in current()]}

  @routes.get("/{name}")
  def get_capability(name: str, principal: Principal = Depends(current_principal)):
    found = next((item for item in current() if item["name"] == name), None)
    if found is None:
      raise HTTPException(404, f"capability '{name}' not found (capabilities: {', '.join(SUBSYSTEMS)})")
    return visible(found, principal)

  return routes
