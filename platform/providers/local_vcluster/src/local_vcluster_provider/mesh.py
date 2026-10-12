"""Istio (sidecar) and the Gateway API CRDs in each vcluster (ADR 0035), from the charts and the bundle
baked into the image.

Installed against the vcluster API at its in-cluster address (https://vcluster.env-<name>, the chart's
Service): the kubeconfig the vcluster exports points to 127.0.0.1, for the host. The Gateway API CRDs go
by server-side apply: client-side apply would keep a last-applied annotation, and the one of httproutes
alone is over the 256 KiB limit of an annotation.
"""
import os
import subprocess
import tempfile

import yaml
from kubernetes import client, config, dynamic

ISTIO_VERSION = os.environ.get("ISTIO_VERSION", "1.30.5")
GATEWAY_API_VERSION = os.environ.get("GATEWAY_API_VERSION", "v1.5.1")
BASE_CHART = "/charts/istio-base.tgz"
ISTIOD_CHART = "/charts/istiod.tgz"
GATEWAY_API = "/manifests/gateway-api.yaml"
NAMESPACE = "istio-system"
MANAGER = "platform-local-vcluster"
SERVER = "https://vcluster.env-{name}"

# The chart asks 500m/2 GiB for istiod and 100m/128 MiB per sidecar, sized for a shared cluster; the spike
# measured 42 MiB of istiod and ~50 MiB per proxy with a few pods.
ISTIOD_VALUES = {
  "pilot": {"autoscaleEnabled": False, "replicaCount": 1, "resources": {"requests": {"cpu": "50m", "memory": "128Mi"}}},
  "global": {"proxy": {"resources": {"requests": {"cpu": "10m", "memory": "64Mi"}}}},
}


class MeshError(Exception):
  pass


def wanted() -> dict:
  return {"istio": ISTIO_VERSION, "gatewayAPI": GATEWAY_API_VERSION}


def in_cluster(kubeconfig: str, name: str, server: str = SERVER) -> dict:
  data = yaml.safe_load(kubeconfig)
  data["clusters"][0]["cluster"]["server"] = server.format(name=name)
  return data


class Mesh:
  def __init__(self, base_chart: str = BASE_CHART, istiod_chart: str = ISTIOD_CHART, gateway_api: str = GATEWAY_API, server: str = SERVER):
    self.base_chart, self.istiod_chart, self.gateway_api, self.server = base_chart, istiod_chart, gateway_api, server

  def _client(self, name: str, kubeconfig: str) -> client.ApiClient:
    return config.new_client_from_config_dict(in_cluster(kubeconfig, name, self.server))

  def _helm(self, name: str, kubeconfig: str, *args: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as file:
      yaml.safe_dump(in_cluster(kubeconfig, name, self.server), file)
      file.flush()
      try:
        result = subprocess.run(["helm", "--kubeconfig", file.name, *args], check=True, capture_output=True, text=True)
      except subprocess.CalledProcessError as error:
        raise MeshError((error.stderr or error.stdout).strip()) from error
    return result.stdout

  def install(self, name: str, kubeconfig: str) -> None:
    """Gateway API CRDs first (istiod watches them when it starts), then istio/base and istio/istiod."""
    api = dynamic.DynamicClient(self._client(name, kubeconfig))
    with open(self.gateway_api) as file:
      for obj in yaml.safe_load_all(file):
        if not obj:
          continue
        resource = api.resources.get(api_version=obj["apiVersion"], kind=obj["kind"])
        api.server_side_apply(resource, body=obj, field_manager=MANAGER, force_conflicts=True)
    self._helm(name, kubeconfig, "upgrade", "--install", "istio-base", self.base_chart, "--namespace", NAMESPACE, "--create-namespace")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as values:
      yaml.safe_dump(ISTIOD_VALUES, values)
      values.flush()
      self._helm(name, kubeconfig, "upgrade", "--install", "istiod", self.istiod_chart, "--namespace", NAMESPACE, "--values", values.name)

  def ready(self, name: str, kubeconfig: str) -> bool:
    try:
      deployment = client.AppsV1Api(self._client(name, kubeconfig)).read_namespaced_deployment("istiod", NAMESPACE)
    except client.ApiException as error:
      if error.status == 404:
        return False
      raise
    return (deployment.status.available_replicas or 0) >= 1
