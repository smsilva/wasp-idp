import json
import socket
import subprocess
from pathlib import Path


class K3d:
  """The k3d operations the provider needs. Runs on the host because it drives Docker."""

  def exists(self, cluster: str) -> bool:
    result = subprocess.run(["k3d", "cluster", "list", "--output", "json"], check=True, capture_output=True, text=True)
    return any(item["name"] == cluster for item in json.loads(result.stdout or "[]"))

  def create(self, cluster: str) -> None:
    subprocess.run(
      [
        "k3d", "cluster", "create", cluster,
        "--api-port", f"127.0.0.1:{free_port()}",
        "--kubeconfig-update-default=false",
        "--kubeconfig-switch-context=false",
        "--wait",
        "--timeout", "300s",
      ],
      check=True,
      capture_output=True,
      text=True,
    )

  def delete(self, cluster: str) -> None:
    subprocess.run(["k3d", "cluster", "delete", cluster], check=True, capture_output=True, text=True)

  def write_kubeconfig(self, cluster: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
      ["k3d", "kubeconfig", "write", cluster, "--output", str(path), "--overwrite"],
      check=True,
      capture_output=True,
      text=True,
    )
    path.chmod(0o600)


def free_port() -> int:
  with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    return probe.getsockname()[1]
