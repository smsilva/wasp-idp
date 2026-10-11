"""vcluster as a Helm release per environment, from the chart baked into the image."""
import json
import subprocess
import tempfile

import yaml

CHART = "/charts/vcluster.tgz"


class HelmError(Exception):
  pass


# The host port goes on a Service of its own (#307). The vcluster mirrors the ports of its main Service
# in the virtual default/kubernetes, but injects KUBERNETES_SERVICE_PORT=443 in every pod: with the
# main Service on the host port, CoreDNS (and any in-cluster client) never reaches the API.
HOST_SERVICE = "vcluster-host"


def host_service(port: int) -> str:
  return yaml.safe_dump({
    "apiVersion": "v1",
    "kind": "Service",
    "metadata": {"name": HOST_SERVICE, "labels": {"app": "vcluster", "release": "vcluster"}},
    "spec": {
      "type": "LoadBalancer",
      "selector": {"app": "vcluster", "release": "vcluster"},
      "ports": [{"name": "https", "port": port, "targetPort": 8443, "protocol": "TCP"}],
    },
  }, sort_keys=False)


def values(port: int) -> dict:
  """Control plane reachable from the host: the chart's Service stays ClusterIP on 443 for the pods,
  a second Service (LoadBalancer) publishes the host port, and the certificate is valid for 127.0.0.1."""
  return {
    "controlPlane": {
      "proxy": {"extraSANs": ["127.0.0.1", "localhost"]},
    },
    "experimental": {"deploy": {"host": {"manifests": host_service(port)}}},
    "exportKubeConfig": {"server": f"https://127.0.0.1:{port}"},
    "telemetry": {"enabled": False},
  }


class Helm:
  def __init__(self, chart: str = CHART):
    self.chart = chart

  def _run(self, *args: str) -> str:
    try:
      result = subprocess.run(["helm", *args], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
      raise HelmError((error.stderr or error.stdout).strip()) from error
    return result.stdout

  def installed(self, release: str, namespace: str) -> bool:
    releases = json.loads(self._run("list", "--namespace", namespace, "--filter", f"^{release}$", "--output", "json") or "[]")
    return any(r["name"] == release for r in releases)

  def install(self, release: str, namespace: str, port: int) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as file:
      yaml.safe_dump(values(port), file)
      file.flush()
      self._run(
        "upgrade", "--install", release, self.chart,
        "--namespace", namespace, "--create-namespace",
        "--values", file.name,
      )

  def uninstall(self, release: str, namespace: str) -> None:
    self._run("uninstall", release, "--namespace", namespace, "--ignore-not-found", "--wait")
