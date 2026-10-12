"""dns and route provisioners (ADR 0036, #358): an instance reached from outside its environment.

Both read the entry point of the environment, status.ingress (domain and host port), written by the
local_vcluster provider: every host under *.<domain> reaches Gateway platform of the vcluster.

dns/provision makes nothing: its output host is <instance>.<domain>, a name the entry point already sends
to the Gateway.

route/provision: an HTTPRoute in namespace apps of the vcluster, attached to Gateway platform, that sends
params.host and the prefix params.path to the Service of the instance on params.port. The host is the instance's own name under the domain of its
environment (<instance>.<domain>, or a name under it): a Score never takes the host of another instance,
nor of another environment, whose Gateway would refuse it anyway. Named and owned
like the objects of postgres/provision: an HTTPRoute of another request is refused, never taken over.
Ready once the Gateway accepted it: the Service comes later, applied by the workload provider when every
resource is Ready. Its output url is where the instance is reached.
"""
import re

from .postgres import DNS_LABEL, HOST, MANAGER, OWNER, SECRET_NAMESPACE, InvalidName, _owned, object_name

GATEWAY_API = "gateway.networking.k8s.io/v1"
# Must match GATEWAY and GATEWAY_NAMESPACE in platform/providers/local_vcluster/src/local_vcluster_provider/entrypoint.py.
GATEWAY = "platform"
GATEWAY_NAMESPACE = "istio-ingress"
PATH = re.compile(r"/[A-Za-z0-9._~/-]{0,255}")


def entry_point(environment: dict | None, name: str) -> dict:
  ingress = ((environment or {}).get("status") or {}).get("ingress") or {}
  if not ingress.get("domain") or not ingress.get("port"):
    raise InvalidName(f"environment {name} has no entry point (status.ingress): its provider predates ADR 0036")
  return ingress


def url_of(host: str, port: int, path: str) -> str:
  return f"http://{host}" + (f":{port}" if port != 80 else "") + path


def accepted(route: dict | None) -> tuple[str | None, str]:
  """The Accepted condition the Gateway wrote on the route: (status, message)."""
  for parent in ((route or {}).get("status") or {}).get("parents") or []:
    if (parent.get("parentRef") or {}).get("name") != GATEWAY:
      continue
    for condition in parent.get("conditions") or []:
      if condition.get("type") == "Accepted":
        return condition.get("status"), condition.get("message") or condition.get("reason") or ""
  return None, ""


def route_params(params: dict, instance: str, domain: str) -> tuple[str, str, int]:
  host, own = str(params.get("host") or ""), f"{instance}.{domain}"
  if not HOST.fullmatch(host) or len(host) > 253 or not (host == own or host.endswith(f".{own}")):
    raise InvalidName(f"route needs params.host {own} (the host of resource dns) or a name under it, got {params.get('host')!r}")
  path = str(params.get("path") or "/")
  if not PATH.fullmatch(path):
    raise InvalidName(f"route needs params.path as an absolute path, got {params.get('path')!r}")
  try:
    port = int(params.get("port"))
  except (TypeError, ValueError):
    port = 0
  if not 1 <= port <= 65535:
    raise InvalidName(f"route needs params.port, the port of the Service, got {params.get('port')!r}")
  return host, path, port


def manifest(request: dict, name: str, host: str, path: str, port: int) -> dict:
  instance = request["spec"]["instance"]
  return {
    "apiVersion": GATEWAY_API,
    "kind": "HTTPRoute",
    "metadata": {
      "name": name,
      "namespace": SECRET_NAMESPACE,
      "labels": {"app.kubernetes.io/instance": instance, "app.kubernetes.io/managed-by": MANAGER},
      "annotations": {OWNER: request["metadata"]["name"]},
    },
    "spec": {
      "parentRefs": [{"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": GATEWAY, "namespace": GATEWAY_NAMESPACE}],
      "hostnames": [host],
      "rules": [{"matches": [{"path": {"type": "PathPrefix", "value": path}}], "backendRefs": [{"name": instance, "port": port}]}],
    },
  }


class Dns:
  def __init__(self, environments):
    self.environments = environments  # name -> Environment (store.get_environment)

  def ensure(self, request: dict, params: dict, vcluster, secrets) -> tuple[str, str, dict, dict | None]:
    spec = request["spec"]
    if not DNS_LABEL.fullmatch(spec["instance"]):
      raise InvalidName(f"{spec['instance']!r} is not a valid name")
    host = f"{spec['instance']}.{entry_point(self.environments(spec['environment']), spec['environment'])['domain']}"
    return "Ready", host, {"host": host}, None

  def delete(self, request: dict, vcluster, secrets) -> None:
    pass


class Route:
  # The only params a Score sets: the policy decides everything else of every provisioner.
  score_params = ("host", "path", "port")

  def __init__(self, environments):
    self.environments = environments

  def ensure(self, request: dict, params: dict, vcluster, secrets) -> tuple[str, str, dict, dict | None]:
    spec = request["spec"]
    entry = entry_point(self.environments(spec["environment"]), spec["environment"])
    host, path, port = route_params(params, spec["instance"], entry["domain"])
    name, owner = object_name(request), request["metadata"]["name"]
    if not _owned(vcluster.get(GATEWAY_API, "HTTPRoute", SECRET_NAMESPACE, name), owner):
      raise InvalidName(f"HTTPRoute {SECRET_NAMESPACE}/{name} already exists and belongs to something else")
    vcluster.apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": SECRET_NAMESPACE}}, MANAGER)
    vcluster.apply(manifest(request, name, host, path, port), MANAGER)
    url = url_of(host, entry["port"], path)
    outputs = {"host": host, "path": path, "url": url}
    status, message = accepted(vcluster.get(GATEWAY_API, "HTTPRoute", SECRET_NAMESPACE, name))
    if status == "True":
      return "Ready", f"{url} routed to {spec['instance']}:{port}", outputs, None
    if status == "False":
      return "Failed", f"the gateway refused the route of {host}: {message}", outputs, None
    return "Provisioning", f"waiting for the gateway to accept the route of {host}", outputs, None

  def delete(self, request: dict, vcluster, secrets) -> None:
    name, owner = object_name(request), request["metadata"]["name"]
    if vcluster is not None and _owned(vcluster.get(GATEWAY_API, "HTTPRoute", SECRET_NAMESPACE, name), owner):
      vcluster.delete(GATEWAY_API, "HTTPRoute", SECRET_NAMESPACE, name)
