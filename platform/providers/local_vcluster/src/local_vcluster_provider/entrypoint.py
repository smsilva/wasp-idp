"""The HTTP entry point of each environment (ADR 0036): a Gateway of the mesh in the vcluster, reached from
the host through the shared Traefik of platform-local.

In the vcluster, Gateway `platform` (class istio) in namespace istio-ingress: Istio makes its Deployment and
the Service platform-istio, ClusterIP (annotation), so the vcluster syncs it to the host without a k3s
svclb. On the host, an Ingress of class platform in env-<name> sends *.<name>.<domain> to that synced
Service. Traefik publishes one host port for every environment (127.0.0.1:7080) and tells them apart by host.
Routes (HTTPRoute, #358) attach to the Gateway from any namespace of the vcluster.
"""
from kubernetes import client, config, dynamic

from .mesh import SERVER, in_cluster

GATEWAY_API = "gateway.networking.k8s.io/v1"
GATEWAY = "platform"
GATEWAY_NAMESPACE = "istio-ingress"
# The Deployment and Service Istio makes for the Gateway (<gateway>-<class>); the Service as the vcluster
# syncs it to the host: <name>-x-<namespace>-x-<release>.
DEPLOYMENT = f"{GATEWAY}-istio"
HOST_SERVICE = f"{DEPLOYMENT}-x-{GATEWAY_NAMESPACE}-x-vcluster"
INGRESS = "gateway"
INGRESS_CLASS = "platform"
MANAGER = "platform-local-vcluster"
# *.localhost resolves to the loopback without DNS (RFC 6761).
DOMAIN = "localhost"
# Must match INGRESS_PORT in cli/src/wasp_platform/bootstrap/local.py, the host port platform init maps.
PORT = 7080


def domain_of(name: str, domain: str = DOMAIN) -> str:
  return f"{name}.{domain}"


def gateway(name: str, domain: str = DOMAIN) -> list[dict]:
  return [
    {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": GATEWAY_NAMESPACE}},
    {
      "apiVersion": GATEWAY_API,
      "kind": "Gateway",
      "metadata": {
        "name": GATEWAY,
        "namespace": GATEWAY_NAMESPACE,
        "labels": {"app.kubernetes.io/managed-by": MANAGER},
        "annotations": {"networking.istio.io/service-type": "ClusterIP"},
      },
      "spec": {
        "gatewayClassName": "istio",
        "listeners": [{
          "name": "http",
          "hostname": f"*.{domain_of(name, domain)}",
          "port": 80,
          "protocol": "HTTP",
          "allowedRoutes": {"namespaces": {"from": "All"}},
        }],
      },
    },
  ]


def ingress(name: str, namespace: str, domain: str = DOMAIN) -> dict:
  return {
    "apiVersion": "networking.k8s.io/v1",
    "kind": "Ingress",
    "metadata": {"name": INGRESS, "namespace": namespace, "labels": {"app.kubernetes.io/managed-by": MANAGER}},
    "spec": {
      "ingressClassName": INGRESS_CLASS,
      "rules": [{
        "host": f"*.{domain_of(name, domain)}",
        "http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {"service": {"name": HOST_SERVICE, "port": {"number": 80}}}}]},
      }],
    },
  }


def programmed(obj: dict | None) -> bool:
  conditions = ((obj or {}).get("status") or {}).get("conditions") or []
  return any(c.get("type") == "Programmed" and c.get("status") == "True" for c in conditions)


class Entrypoint:
  def __init__(self, domain: str = DOMAIN, port: int = PORT, server: str = SERVER):
    self.domain, self.port, self.server = domain, port, server

  def wanted(self, name: str) -> dict:
    return {"domain": domain_of(name, self.domain), "port": self.port}

  def _vcluster(self, name: str, kubeconfig: str) -> dynamic.DynamicClient:
    return dynamic.DynamicClient(config.new_client_from_config_dict(in_cluster(kubeconfig, name, self.server)))

  def install(self, name: str, kubeconfig: str, namespace: str) -> None:
    """The Gateway in the vcluster, then the Ingress on the host; both by server-side apply."""
    api = self._vcluster(name, kubeconfig)
    for obj in gateway(name, self.domain):
      resource = api.resources.get(api_version=obj["apiVersion"], kind=obj["kind"])
      api.server_side_apply(resource, body=obj, field_manager=MANAGER, force_conflicts=True)
    host = dynamic.DynamicClient(client.ApiClient())
    obj = ingress(name, namespace, self.domain)
    resource = host.resources.get(api_version=obj["apiVersion"], kind=obj["kind"])
    host.server_side_apply(resource, body=obj, namespace=namespace, field_manager=MANAGER, force_conflicts=True)

  def ready(self, name: str, kubeconfig: str) -> bool:
    """Programmed and serving: Istio programs the Gateway as soon as its Service exists, before the pod
    of the gateway is up, and a request then gets no answer."""
    api = self._vcluster(name, kubeconfig)
    gateways = api.resources.get(api_version=GATEWAY_API, kind="Gateway")
    deployments = api.resources.get(api_version="apps/v1", kind="Deployment")
    try:
      obj = gateways.get(name=GATEWAY, namespace=GATEWAY_NAMESPACE).to_dict()
      deployment = deployments.get(name=DEPLOYMENT, namespace=GATEWAY_NAMESPACE).to_dict()
    except dynamic.exceptions.NotFoundError:
      return False
    return programmed(obj) and ((deployment.get("status") or {}).get("availableReplicas") or 0) >= 1
