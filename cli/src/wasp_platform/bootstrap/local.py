import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import yaml

from .. import config

CLUSTER = "platform-local"
CONTEXT = f"k3d-{CLUSTER}"
NAMESPACE = "platform-system"
API_PORT = "6560"
APP_PORT = "9090"
API_URL = f"http://127.0.0.1:{APP_PORT}"
IMAGE = "platform-api"
AUTH_NAMESPACE = "platform-auth"
KEYCLOAK_PORT = "8180"
# Must match KC_HOSTNAME in platform/keycloak/deploy/keycloak.yaml: it is the `iss` of every token.
KEYCLOAK_URL = f"http://localhost:{KEYCLOAK_PORT}"
ISSUER = f"{KEYCLOAK_URL}/realms/platform"
CLI_CLIENT_ID = "platform-cli"


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


def _ensure_keycloak_port(log) -> None:
  """Clusters created before Keycloak lack the 8180 mapping; k3d can add it to the load balancer."""
  clusters = json.loads(_run("k3d", "cluster", "list", CLUSTER, "--output", "json"))
  ports = json.dumps(clusters[0].get("nodes", []))
  if f'"HostPort": "{KEYCLOAK_PORT}"' in ports:
    return
  log(f"adding port {KEYCLOAK_PORT} to cluster {CLUSTER} …")
  _run("k3d", "cluster", "edit", CLUSTER, "--port-add", f"127.0.0.1:{KEYCLOAK_PORT}:{KEYCLOAK_PORT}@loadbalancer")


def _secret_value(namespace: str, name: str, key: str) -> str | None:
  try:
    encoded = _kubectl("get", "secret", name, "--namespace", namespace, "--output", f"jsonpath={{.data.{key}}}")
  except BootstrapError:
    return None
  return base64.b64decode(encoded).decode() if encoded else None


def _apply_secret(namespace: str, name: str, values: dict[str, str]) -> None:
  manifest = {
    "apiVersion": "v1", "kind": "Secret", "type": "Opaque",
    "metadata": {"name": name, "namespace": namespace},
    "stringData": values,
  }
  _kubectl("apply", "--filename", "-", input=json.dumps(manifest))


def render_realm(realm: dict, google: bool, admin: bool) -> dict:
  """Drop the Google identity provider without credentials, and the bootstrap-admin mapper without --admin."""
  realm = dict(realm)
  if not google:
    realm.pop("identityProviders", None)
    realm.pop("identityProviderMappers", None)
  elif not admin:
    realm["identityProviderMappers"] = [m for m in realm.get("identityProviderMappers", []) if m["name"] != "bootstrap-admin"]
  return realm


def install_keycloak(root: Path, admin_email: str | None, log) -> dict:
  keycloak_dir = root / "platform" / "keycloak"
  _kubectl("apply", "--filename", str(keycloak_dir / "deploy" / "keycloak.yaml"))

  # The bootstrap admin password is generated once and kept: Keycloak only reads it on first start.
  if not _secret_value(AUTH_NAMESPACE, "keycloak-admin", "password"):
    _apply_secret(AUTH_NAMESPACE, "keycloak-admin", {"username": "admin", "password": secrets.token_urlsafe(24)})

  # --admin is remembered in the Secret, so a later `init` without it keeps the bootstrap admin.
  admin_email = admin_email or _secret_value(AUTH_NAMESPACE, "keycloak-google", "PLATFORM_ADMIN_EMAIL") or ""
  client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
  client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
  if not (client_id and client_secret):
    client_id = _secret_value(AUTH_NAMESPACE, "keycloak-google", "GOOGLE_CLIENT_ID") or ""
    client_secret = _secret_value(AUTH_NAMESPACE, "keycloak-google", "GOOGLE_CLIENT_SECRET") or ""
  google = bool(client_id and client_secret)
  if not google:
    log("warning: GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET not set — realm without the Google identity provider")
  _apply_secret(AUTH_NAMESPACE, "keycloak-google", {
    "GOOGLE_CLIENT_ID": client_id,
    "GOOGLE_CLIENT_SECRET": client_secret,
    "PLATFORM_ADMIN_EMAIL": admin_email,
  })

  realm = render_realm(yaml.safe_load((keycloak_dir / "realm-platform.yaml").read_text()), google, bool(admin_email))
  configmap = {
    "apiVersion": "v1", "kind": "ConfigMap",
    "metadata": {"name": "keycloak-realm", "namespace": AUTH_NAMESPACE},
    "data": {"realm-platform.yaml": yaml.safe_dump(realm, sort_keys=False)},
  }
  _kubectl("apply", "--filename", "-", input=json.dumps(configmap))

  _apply_theme(keycloak_dir / "theme" / "platform")

  log("waiting for Keycloak …")
  _kubectl("rollout", "status", "deployment/keycloak", "--namespace", AUTH_NAMESPACE, "--timeout", "300s")

  log("applying the realm platform …")
  _kubectl("delete", "job", "keycloak-realm-import", "--namespace", AUTH_NAMESPACE, "--ignore-not-found")
  _kubectl("apply", "--filename", str(keycloak_dir / "deploy" / "realm-import.yaml"))
  try:
    _kubectl("wait", "job/keycloak-realm-import", "--namespace", AUTH_NAMESPACE, "--for", "condition=Complete", "--timeout", "300s")
  except BootstrapError as error:
    logs = _kubectl("logs", "job/keycloak-realm-import", "--namespace", AUTH_NAMESPACE, "--tail", "30")
    raise BootstrapError(f"realm import did not complete:\n{logs}") from error
  wait_issuer(ISSUER)
  return {"issuer": ISSUER, "google": google, "admin": admin_email or None}


def theme_configmap(theme_dir: Path) -> dict:
  """The theme tree as one ConfigMap: keys flatten the path with "__" (the init container rebuilds it)."""
  data = {
    "__".join(path.relative_to(theme_dir).parts): path.read_text()
    for path in sorted(theme_dir.rglob("*")) if path.is_file()
  }
  return {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "keycloak-theme", "namespace": AUTH_NAMESPACE}, "data": data}


def _apply_theme(theme_dir: Path) -> None:
  configmap = theme_configmap(theme_dir)
  _kubectl("apply", "--filename", "-", input=json.dumps(configmap))
  # The theme is copied at pod start: a changed theme needs a new pod, an unchanged one keeps it.
  digest = hashlib.sha256(json.dumps(configmap["data"], sort_keys=True).encode()).hexdigest()[:16]
  patch = {"spec": {"template": {"metadata": {"annotations": {"platform.wasp.silvios.me/theme": digest}}}}}
  _kubectl("patch", "deployment", "keycloak", "--namespace", AUTH_NAMESPACE, "--type", "merge", "--patch", json.dumps(patch))


def wait_issuer(issuer: str, timeout: int = 60) -> None:
  deadline = time.monotonic() + timeout
  while True:
    try:
      response = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=5)
      if response.status_code == 200 and response.json().get("issuer") == issuer:
        return
    except (httpx.TransportError, ValueError):
      pass
    if time.monotonic() > deadline:
      raise BootstrapError(f"Keycloak issuer {issuer} not reachable after {timeout}s")
    time.sleep(2)


def install(admin_email: str | None = None, log=None) -> dict:
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
      "--extra-port", f"127.0.0.1:{KEYCLOAK_PORT}:{KEYCLOAK_PORT}",
    )
  _ensure_keycloak_port(log)

  log("applying CRDs …")
  _kubectl("apply", "--filename", str(root / "platform" / "crds"))
  _kubectl("wait", "crd", "--all", "--for", "condition=Established", "--timeout", "60s")

  # Keycloak first: the Platform API validates tokens against its keys.
  log("deploying Keycloak …")
  identity = install_keycloak(root, admin_email, log)

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

  path = config.save({
    **config.load(),
    "target": "local", "api_url": API_URL, "context": CONTEXT,
    "issuer": identity["issuer"], "client_id": CLI_CLIENT_ID,
  })
  return {"target": "local", "cluster": CLUSTER, "api_url": API_URL, "image": image, "config": str(path), **identity}


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
