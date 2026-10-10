import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from .. import config

CLUSTER = "platform-local"
CONTEXT = f"k3d-{CLUSTER}"
NAMESPACE = "platform-system"
API_PORT = "6560"
APP_PORT = "9090"
API_URL = f"http://127.0.0.1:{APP_PORT}"
IMAGE = "platform-api"


class BootstrapError(Exception):
  pass


def repo_root() -> Path:
  """The wasp-idp checkout: init applies CRDs, manifests and scripts versioned there."""
  root = Path(os.environ.get("PLATFORM_REPO") or Path(__file__).resolve().parents[4])
  if not (root / "platform" / "crds").is_dir():
    raise BootstrapError(f"wasp-idp checkout not found at {root}: install the CLI editable from the repo or set PLATFORM_REPO")
  return root


def _run(*command: str, input: str | None = None, capture: bool = True) -> str:
  try:
    result = subprocess.run(command, check=True, text=True, input=input, capture_output=capture)
  except FileNotFoundError as error:
    raise BootstrapError(f"'{command[0]}' not found in PATH") from error
  except subprocess.CalledProcessError as error:
    raise BootstrapError(f"{' '.join(command[:3])} … failed:\n{(error.stderr or error.stdout or '').strip()}") from error
  return result.stdout if capture else ""


def _kubectl(*args: str, input: str | None = None) -> str:
  return _run("kubectl", "--context", CONTEXT, *args, input=input)


def cluster_exists() -> bool:
  names = _run("k3d", "cluster", "list", "--no-headers").split()
  return CLUSTER in names


def install(log=None) -> dict:
  log = log or (lambda message: None)
  for tool in ("docker", "k3d", "kubectl"):
    if not shutil.which(tool):
      raise BootstrapError(f"'{tool}' not found in PATH")
  root = repo_root()

  if cluster_exists():
    log(f"cluster {CLUSTER} already exists, reusing it")
  else:
    log(f"creating cluster {CLUSTER} …")
    _run(
      str(root / "scripts" / "cluster-zero" / "cluster-create"),
      "--name", CLUSTER,
      "--api-port", API_PORT,
      "--app-port", f"127.0.0.1:{APP_PORT}",
    )

  log("applying CRDs …")
  _kubectl("apply", "--filename", str(root / "platform" / "crds"))
  _kubectl("wait", "crd", "--all", "--for", "condition=Established", "--timeout", "60s")

  api_dir = root / "platform" / "api"
  log("building the Platform API image …")
  _run("docker", "build", "--quiet", "--tag", f"{IMAGE}:dev", str(api_dir))
  # Tag by image id: an unchanged build keeps the same tag and the rollout is a no-op.
  image_id = _run("docker", "image", "inspect", "--format", "{{.Id}}", f"{IMAGE}:dev").strip()
  image = f"{IMAGE}:{image_id.removeprefix('sha256:')[:12]}"
  _run("docker", "tag", f"{IMAGE}:dev", image)
  _run("k3d", "image", "import", image, "--cluster", CLUSTER)

  log("deploying the Platform API …")
  manifest = (api_dir / "deploy" / "platform-api.yaml").read_text().replace(f"image: {IMAGE}:dev", f"image: {image}")
  _kubectl("apply", "--filename", "-", input=manifest)
  _kubectl("rollout", "status", "deployment/platform-api", "--namespace", NAMESPACE, "--timeout", "180s")
  wait_healthy(API_URL)

  path = config.save({**config.load(), "target": "local", "api_url": API_URL, "context": CONTEXT})
  return {"target": "local", "cluster": CLUSTER, "api_url": API_URL, "image": image, "config": str(path)}


def wait_healthy(url: str, timeout: int = 90) -> None:
  deadline = time.monotonic() + timeout
  while True:
    try:
      if httpx.get(f"{url}/healthz", timeout=5).status_code == 200:
        return
    except httpx.TransportError:
      pass
    if time.monotonic() > deadline:
      raise BootstrapError(f"Platform API not healthy at {url}/healthz after {timeout}s")
    time.sleep(2)


def run_provider() -> None:
  """Replace this process with the local k3d provider: it runs on the host because it drives Docker."""
  if not shutil.which("uv"):
    raise BootstrapError("'uv' not found in PATH")
  if not cluster_exists():
    raise BootstrapError(f"cluster {CLUSTER} not found: run 'platform init --target local' first")
  project = repo_root() / "platform" / "providers" / "local_k3d"
  os.execvp("uv", [
    "uv", "run", "--quiet", "--project", str(project),
    "local-k3d-provider",
    "--context", CONTEXT,
    "--namespace", NAMESPACE,
    "--kubeconfig-dir", str(config.config_dir() / "environments"),
  ])
