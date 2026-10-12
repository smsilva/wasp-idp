"""From a WorkloadRoute to the GAMMA HTTPRoute of a component in its vcluster (ADR 0035, #344).

One HTTPRoute per component, named after it in the namespace apps, with parentRef on the Service of the
main instance (<component>): the mesh applies it to every call made to that Service. Each rule becomes
an HTTPRoute rule in the same order: a header match becomes matches.headers, a baggage match a regular
expression over the baggage header (OpenTelemetry Baggage, key=value entries separated by commas, each
with optional ;properties), and the weights rule backendRefs with weights. A last rule without match
sends the rest to the main instance. The port of each backendRef is the first port of the Service of
its instance. Nothing else of the mesh is written: no VirtualService, no DestinationRule.
"""
import logging
import re
from datetime import datetime, timezone

from .manifests import MANAGER, NAMESPACE

GATEWAY_API = "gateway.networking.k8s.io/v1"
FINALIZER = "platform.wasp.silvios.me/httproute"

log = logging.getLogger("workload-provider")


class MissingService(Exception):
  pass


def baggage_pattern(key: str, value: str) -> str:
  """Matches the entry key=value anywhere in the baggage header. Istio matches the whole header (RE2
  full match), hence the optional prefix and suffix instead of anchors."""
  return rf"(.*,)?\s*{re.escape(key)}\s*=\s*{re.escape(value)}\s*([,;].*)?"


def render_route(route: dict, ports: dict[str, int]) -> dict:
  """The HTTPRoute of the route; ports: the Service port of each instance it names (and the main one)."""
  spec = route["spec"]
  component = spec["component"]

  def backend(instance: str, weight: int | None = None) -> dict:
    if instance not in ports:
      raise MissingService(f"the instance {instance} has no Service in the vcluster")
    ref = {"name": instance, "port": ports[instance]}
    if weight is not None:
      ref["weight"] = weight
    return ref

  rules = []
  for rule in spec.get("rules") or []:
    match = rule.get("match") or {}
    if match.get("header"):
      rules.append({"matches": [{"headers": [{"name": match["header"]["name"], "value": match["header"]["value"]}]}], "backendRefs": [backend(rule["to"])]})
    elif match.get("baggage"):
      header = {"type": "RegularExpression", "name": "baggage", "value": baggage_pattern(match["baggage"]["key"], match["baggage"]["value"])}
      rules.append({"matches": [{"headers": [header]}], "backendRefs": [backend(rule["to"])]})
    elif rule.get("weights"):
      rules.append({"backendRefs": [backend(instance, weight) for instance, weight in sorted(rule["weights"].items())]})
  # What no rule matched goes to the main instance (a weights rule already took it all).
  if not rules or "matches" in rules[-1]:
    rules.append({"backendRefs": [backend(component)]})
  return {
    "apiVersion": GATEWAY_API,
    "kind": "HTTPRoute",
    "metadata": {"name": component, "namespace": NAMESPACE, "labels": {"app.kubernetes.io/name": component, "app.kubernetes.io/managed-by": MANAGER}},
    "spec": {
      "parentRefs": [{"group": "", "kind": "Service", "name": component, "port": ports.get(component)}],
      "rules": rules,
    },
  }


def instances_of(route: dict) -> set[str]:
  """The instances whose Service the HTTPRoute names: the main one and every target."""
  rules = route["spec"].get("rules") or []
  return {route["spec"]["component"]} | {rule["to"] for rule in rules if rule.get("to")} | {name for rule in rules for name in rule.get("weights") or {}}


def accepted(httproute: dict | None) -> tuple[str, str, str]:
  """(status, reason, message) of the route from the conditions the mesh wrote on its parent: True
  once Accepted and ResolvedRefs, Unknown until the mesh has looked at it."""
  parents = ((httproute or {}).get("status") or {}).get("parents") or []
  if not parents:
    return "Unknown", "Pending", "waiting for the mesh to accept the HTTPRoute"
  conditions = {c.get("type"): c for parent in parents for c in parent.get("conditions") or []}
  for kind in ("Accepted", "ResolvedRefs"):
    condition = conditions.get(kind)
    if condition is None:
      return "Unknown", "Pending", f"waiting for the mesh to set {kind}"
    if condition.get("status") != "True":
      return "False", condition.get("reason") or f"Not{kind}", condition.get("message") or kind
  return "True", "Accepted", "the mesh routes the traffic"


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


class RouteReconciler:
  """WorkloadRoutes in, HTTPRoutes out. Every pass applies each route (server-side apply, idempotent,
  so an HTTPRoute changed or deleted by hand comes back) and copies the mesh's verdict to the status.

  A finalizer keeps the WorkloadRoute until its HTTPRoute is gone from the vcluster; when the
  Environment itself is going (or never got a kubeconfig), the vcluster goes with it and the finalizer
  is dropped without touching it, or the delete of the environment would hang on its routes.
  """

  def __init__(self, store, vclusters, now=utcnow):
    self.store = store
    self.vclusters = vclusters
    self.now = now

  def reconcile(self, routes: list[dict]) -> bool:
    """One pass; True while some route waits on the mesh or on an instance (the caller polls faster)."""
    pending = False
    for route in routes:
      try:
        pending |= self._reconcile(route)
      except Exception:  # keep the loop alive; the next pass tries again
        log.exception("route %s failed", route["metadata"]["name"])
        pending = True
    return pending

  def _reconcile(self, route: dict) -> bool:
    spec = route["spec"]
    environment = self.store.get_environment(spec["environment"])
    gone = environment is None or bool(environment["metadata"].get("deletionTimestamp")) or not (environment.get("status") or {}).get("kubeconfigData")
    if route["metadata"].get("deletionTimestamp"):
      if FINALIZER in (route["metadata"].get("finalizers") or []):
        if not gone:
          self.vclusters.of(environment).delete(GATEWAY_API, "HTTPRoute", NAMESPACE, spec["component"])
        self.store.remove_route_finalizer(route, FINALIZER)
        log.info("route %s: HTTPRoute removed", route["metadata"]["name"])
      return False
    if FINALIZER not in (route["metadata"].get("finalizers") or []):
      self.store.add_route_finalizer(route, FINALIZER)
    if gone:
      return False
    if (ready_of(environment) or {}).get("status") != "True":
      return self._status(route, "Unknown", "EnvironmentNotReady", f"environment {spec['environment']} is not ready yet")
    if not (environment.get("status") or {}).get("mesh"):
      return self._status(route, "False", "MeshNotInstalled", f"environment {spec['environment']} has no mesh (created before ADR 0035): create it again to route traffic")
    vcluster = self.vclusters.of(environment)
    ports = {}
    for instance in sorted(instances_of(route)):
      port = vcluster.service_port(NAMESPACE, instance)
      if port is not None:
        ports[instance] = port
    try:
      httproute = render_route(route, ports)
    except MissingService as error:
      return self._status(route, "Unknown", "InstancePending", str(error))
    try:
      vcluster.apply(httproute, MANAGER)
    except Exception as error:
      return self._status(route, "False", "ApplyFailed", f"applying the HTTPRoute in the vcluster of {spec['environment']}: {error}")
    status, reason, message = accepted(vcluster.get(GATEWAY_API, "HTTPRoute", NAMESPACE, spec["component"]))
    return self._status(route, status, reason, message)

  def _status(self, route: dict, status: str, reason: str, message: str) -> bool:
    """Writes the condition when it changed; True while it is not final."""
    generation = route["metadata"].get("generation")
    current = route.get("status") or {}
    ready = ready_of(route) or {}
    if (current.get("observedGeneration"), ready.get("status"), ready.get("reason"), ready.get("message")) != (generation, status, reason, message):
      log.info("route %s: %s (%s)", route["metadata"]["name"], reason, message)
      condition = {"type": "Ready", "status": status, "reason": reason, "message": message[:500], "lastTransitionTime": self.now().strftime("%Y-%m-%dT%H:%M:%SZ")}
      self.store.patch_route_status(route["metadata"]["name"], {"observedGeneration": generation, "conditions": [condition]})
    return status == "Unknown"


def ready_of(obj: dict) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), None)
