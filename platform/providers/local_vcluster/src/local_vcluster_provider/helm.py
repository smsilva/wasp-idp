"""vcluster as a Helm release per environment, from the chart baked into the image."""
import json
import subprocess
import tempfile

import yaml

CHART = "/charts/vcluster.tgz"


class HelmError(Exception):
  pass


def values(port: int) -> dict:
  """Control plane reachable from the host: LoadBalancer on its own port, certificate valid for 127.0.0.1."""
  return {
    "controlPlane": {
      "service": {"spec": {"type": "LoadBalancer", "ports": [{"name": "https", "port": port, "targetPort": 8443, "protocol": "TCP"}]}},
      "proxy": {"extraSANs": ["127.0.0.1", "localhost"]},
    },
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
