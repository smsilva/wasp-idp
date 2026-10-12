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
from .admin_permissions import AdminPermissions

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
# Test client and users of scripts/demo/cli-smoke (#179, realm-smoke.yaml): local target only.
SMOKE_CLIENT_ID = "platform-smoke"
SMOKE_USER = "platform-smoke"
SMOKE_ADMIN = "platform-smoke-admin"
# A second plain user, for sharing an environment with a teammate (#232).
SMOKE_MEMBER = "platform-smoke-member"
SMOKE_SECRET = "keycloak-smoke-user"
SMOKE_KEYS = {SMOKE_USER: "SMOKE_USER_PASSWORD", SMOKE_ADMIN: "SMOKE_ADMIN_PASSWORD", SMOKE_MEMBER: "SMOKE_MEMBER_PASSWORD"}
# Secret of the platform-api-admin client (teams, #231): read by the realm import and by the API.
API_ADMIN_SECRET = "platform-api-keycloak"
API_ADMIN_KEY = "PLATFORM_API_ADMIN_SECRET"
# One host port per vcluster environment (provider local_vcluster, #183); must match PORTS in
# platform/providers/local_vcluster/src/local_vcluster_provider/reconciler.py.
ENV_PORTS = "7100-7119"
# The shared Traefik in front of every environment (ADR 0036): workloads at http://*.<environment>.localhost:7080.
# Must match PORT in platform/providers/local_vcluster/src/local_vcluster_provider/entrypoint.py.
INGRESS_PORT = "7080"
INGRESS_NAMESPACE = "platform-ingress"
PROVIDER_IMAGE = "local-vcluster-provider"
# Cloud accounts (ADR 0029): the base credential the aws_account controller assumes roles from.
AWS_PROVIDER_IMAGE = "aws-account-provider"
AWS_BASE_SECRET = "aws-base-credential"

SCM_PROVIDER_IMAGE = "scm-github-provider"
# Workload Instances (ADR 0033): applies each WorkloadRevision in the vcluster of its Environment.
WORKLOAD_PROVIDER_IMAGE = "workload-provider"
FORAGER_PROVIDER_IMAGE = "forager-provider"
# The shared instance of postgres in mode compose and its admin password (#305).
SHARED_PG_NAMESPACE = "platform-resources"
SHARED_PG_SECRET = "shared-pg-admin"
# Factory templates (ADR 0024): read from this public repo, so no credential is needed.
SEED_REPO = "https://github.com/smsilva/wasp-idp"
SEED_FOLDER = Path("platform") / "templates"
CATALOG_API_VERSION = "catalog.platform.wasp.silvios.me/v1alpha1"


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


def _ensure_port(ports: str, log) -> None:
  """Clusters created by an older init lack newer mappings; k3d can add them to the load balancer."""
  clusters = json.loads(_run("k3d", "cluster", "list", CLUSTER, "--output", "json"))
  mapped = json.dumps(clusters[0].get("nodes", []))
  if f'"HostPort": "{ports.split("-")[0]}"' in mapped:
    return
  log(f"adding port {ports} to cluster {CLUSTER} …")
  _run("k3d", "cluster", "edit", CLUSTER, "--port-add", f"127.0.0.1:{ports}:{ports}@loadbalancer")


def _build_and_import(name: str, context: Path, dockerfile: Path | None = None) -> str:
  """Build, tag by image id and import into platform-local: an unchanged build keeps the tag, so the rollout is a no-op.
  dockerfile: when the context is wider than the project folder (a project with path dependencies)."""
  file = ["--file", str(dockerfile)] if dockerfile else []
  # Without provenance: its attestation changes the image id on every build (containerd image store),
  # so an unchanged project would get a new tag and a rollout on every init.
  _run("docker", "build", "--quiet", "--provenance=false", *file, "--tag", f"{name}:dev", str(context))
  image_id = _run("docker", "image", "inspect", "--format", "{{.Id}}", f"{name}:dev").strip()
  image = f"{name}:{image_id.removeprefix('sha256:')[:12]}"
  _run("docker", "tag", f"{name}:dev", image)
  _run("k3d", "image", "import", image, "--cluster", CLUSTER)
  return image


def _deploy(manifest_path: Path, name: str, image: str) -> None:
  manifest = manifest_path.read_text().replace(f"image: {name}:dev", f"image: {image}")
  _kubectl("apply", "--filename", "-", input=manifest)


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


def _ensure_namespace(name: str) -> None:
  _kubectl("apply", "--filename", "-", input=json.dumps({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": name}}))


def smoke_password(username: str) -> str:
  """The test user's password, from the Secret init generated (the CLI never stores it)."""
  password = _secret_value(AUTH_NAMESPACE, SMOKE_SECRET, SMOKE_KEYS[username])
  if not password:
    raise BootstrapError(f"test user {username} not found: run 'platform init --target local' first")
  return password


def render_realm(realm: dict, google: bool, admin: bool, smoke: dict | None = None) -> dict:
  """Drop the Google identity provider without credentials, and the bootstrap-admin mapper without --admin.
  With smoke (realm-smoke.yaml, local target only), add the test client and users of #179."""
  realm = dict(realm)
  if smoke:
    realm["clients"] = [*realm.get("clients", []), *smoke.get("clients", [])]
    realm["users"] = [*realm.get("users", []), *smoke.get("users", [])]
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

  # Test identities of #179, generated once; local target only (realm-smoke.yaml explains why).
  smoke_secret = {key: _secret_value(AUTH_NAMESPACE, SMOKE_SECRET, key) or secrets.token_urlsafe(24) for key in SMOKE_KEYS.values()}
  _apply_secret(AUTH_NAMESPACE, SMOKE_SECRET, smoke_secret)
  smoke = yaml.safe_load((keycloak_dir / "realm-smoke.yaml").read_text())

  # Generated once; the Platform API namespace may not exist yet on a fresh cluster.
  admin_secret = _secret_value(AUTH_NAMESPACE, API_ADMIN_SECRET, API_ADMIN_KEY) or secrets.token_urlsafe(32)
  for namespace in (AUTH_NAMESPACE, NAMESPACE):
    _ensure_namespace(namespace)
    _apply_secret(namespace, API_ADMIN_SECRET, {API_ADMIN_KEY: admin_secret})

  realm = render_realm(yaml.safe_load((keycloak_dir / "realm-platform.yaml").read_text()), google, bool(admin_email), smoke)
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

  log("applying the admin permissions of the Platform API …")
  try:
    AdminPermissions(
      KEYCLOAK_URL,
      _secret_value(AUTH_NAMESPACE, "keycloak-admin", "username"),
      _secret_value(AUTH_NAMESPACE, "keycloak-admin", "password"),
    ).apply(log)
  except httpx.HTTPError as error:
    raise BootstrapError(f"admin permissions of {API_ADMIN_SECRET} not applied: {error}") from error
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


def aws_base_credential(profile: str) -> dict:
  """The profile's credential as the controller's environment; SSO and assumed roles carry an Expiration."""
  exported = json.loads(_run("aws", "configure", "export-credentials", "--profile", profile, "--format", "process"))
  values = {"AWS_ACCESS_KEY_ID": exported["AccessKeyId"], "AWS_SECRET_ACCESS_KEY": exported["SecretAccessKey"]}
  if exported.get("SessionToken"):
    values["AWS_SESSION_TOKEN"] = exported["SessionToken"]
  return {"values": values, "expiration": exported.get("Expiration")}


def install_aws_account(root: Path, aws_profile: str | None, log) -> dict:
  """With --aws-profile, store the base credential; with it stored (now or by an earlier init), deploy
  the controller. Without one, cloud accounts stay NoProviderForCapability."""
  expiration = None
  if aws_profile:
    credential = aws_base_credential(aws_profile)
    expiration = credential["expiration"]
    # Replaced whole: a long-lived key must not keep the session token of an earlier temporary one.
    _kubectl("delete", "secret", AWS_BASE_SECRET, "--namespace", NAMESPACE, "--ignore-not-found")
    _apply_secret(NAMESPACE, AWS_BASE_SECRET, credential["values"])
    if expiration:
      log(f"warning: the credential of profile {aws_profile} expires at {expiration}: run init again after that, or use a dedicated IAM user")
  values = {key: _secret_value(NAMESPACE, AWS_BASE_SECRET, key) for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")}
  if not values["AWS_ACCESS_KEY_ID"]:
    return {"cloud_account": False}

  provider_dir = root / "platform" / "providers" / "aws_account"
  log("building the cloud account provider image …")
  image = _build_and_import(AWS_PROVIDER_IMAGE, provider_dir)
  log("deploying the cloud account provider (aws_account) …")
  _deploy(provider_dir / "deploy" / "aws-account-provider.yaml", AWS_PROVIDER_IMAGE, image)
  # The credential reaches the pod as environment: a new one needs a new pod, an unchanged one keeps it.
  digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:16]
  patch = {"spec": {"template": {"metadata": {"annotations": {"platform.wasp.silvios.me/credential": digest}}}}}
  _kubectl("patch", "deployment", AWS_PROVIDER_IMAGE, "--namespace", NAMESPACE, "--type", "merge", "--patch", json.dumps(patch))
  _kubectl("rollout", "status", f"deployment/{AWS_PROVIDER_IMAGE}", "--namespace", NAMESPACE, "--timeout", "180s")
  return {"cloud_account": True, "aws_base_expires": expiration}


def install(admin_email: str | None = None, log=None, aws_profile: str | None = None) -> dict:
  log = log or (lambda message: None)
  for tool in ("docker", "k3d", "kubectl", *(("aws",) if aws_profile else ())):
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
      "--extra-port", f"127.0.0.1:{ENV_PORTS}:{ENV_PORTS}",
      "--extra-port", f"127.0.0.1:{INGRESS_PORT}:{INGRESS_PORT}",
    )
  _ensure_port(KEYCLOAK_PORT, log)
  _ensure_port(ENV_PORTS, log)
  _ensure_port(INGRESS_PORT, log)

  log("applying CRDs …")
  _kubectl("apply", "--filename", str(root / "platform" / "crds"))
  _kubectl("wait", "crd", "--all", "--for", "condition=Established", "--timeout", "60s")

  # Keycloak first: the Platform API validates tokens against its keys.
  log("deploying Keycloak …")
  identity = install_keycloak(root, admin_email, log)

  api_dir = root / "platform" / "api"
  log("building the Platform API image …")
  # Context platform/: the API depends on platform/libs/templates and platform/libs/score by path.
  image = _build_and_import(IMAGE, api_dir.parent, api_dir / "Dockerfile")

  log("deploying the Platform API …")
  _deploy(api_dir / "deploy" / "platform-api.yaml", IMAGE, image)
  _kubectl("rollout", "status", "deployment/platform-api", "--namespace", NAMESPACE, "--timeout", "180s")
  wait_healthy(API_URL)

  provider_dir = root / "platform" / "providers" / "local_vcluster"
  log("building the environment provider image …")
  provider_image = _build_and_import(PROVIDER_IMAGE, provider_dir)
  log("deploying the environment provider (local_vcluster) …")
  _deploy(provider_dir / "deploy" / "local-vcluster-provider.yaml", PROVIDER_IMAGE, provider_image)
  _kubectl("rollout", "status", "deployment/local-vcluster-provider", "--namespace", NAMESPACE, "--timeout", "180s")
  install_ingress(provider_dir, log)

  scm_dir = root / "platform" / "providers" / "scm_github"
  log("building the SCM provider image …")
  scm_image = _build_and_import(SCM_PROVIDER_IMAGE, scm_dir.parent.parent, scm_dir / "Dockerfile")
  log("deploying the SCM provider (scm_github) …")
  _deploy(scm_dir / "deploy" / "scm-github-provider.yaml", SCM_PROVIDER_IMAGE, scm_image)
  _kubectl("rollout", "status", "deployment/scm-github-provider", "--namespace", NAMESPACE, "--timeout", "180s")

  workload_dir = root / "platform" / "providers" / "workload"
  log("building the workload provider image …")
  workload_image = _build_and_import(WORKLOAD_PROVIDER_IMAGE, workload_dir)
  log("deploying the workload provider (workload) …")
  _deploy(workload_dir / "deploy" / "workload-provider.yaml", WORKLOAD_PROVIDER_IMAGE, workload_image)
  _kubectl("rollout", "status", f"deployment/{WORKLOAD_PROVIDER_IMAGE}", "--namespace", NAMESPACE, "--timeout", "180s")

  forager_dir = root / "platform" / "providers" / "forager"
  log("building the Forager image …")
  forager_image = _build_and_import(FORAGER_PROVIDER_IMAGE, forager_dir)
  log("deploying the Forager (resources of each workload) …")
  _deploy(forager_dir / "deploy" / "forager-provider.yaml", FORAGER_PROVIDER_IMAGE, forager_image)
  _kubectl("rollout", "status", f"deployment/{FORAGER_PROVIDER_IMAGE}", "--namespace", NAMESPACE, "--timeout", "180s")
  install_shared_pg(forager_dir, log)
  install_profile_policies(forager_dir, log)

  cloud = install_aws_account(root, aws_profile, log)
  install_templates(root, log)

  path = config.save({
    **config.load(),
    "target": "local", "api_url": API_URL, "context": CONTEXT,
    "issuer": identity["issuer"], "client_id": CLI_CLIENT_ID,
  })
  return {"target": "local", "cluster": CLUSTER, "api_url": API_URL, "image": image, "config": str(path), **identity, **cloud}


def install_ingress(provider_dir: Path, log) -> None:
  """The shared Traefik of the environments (ADR 0036), through the helm-controller of k3s."""
  log(f"deploying the environments' entry point (Traefik on 127.0.0.1:{INGRESS_PORT}) …")
  _kubectl("apply", "--filename", str(provider_dir / "deploy" / "traefik.yaml"))
  deadline = time.monotonic() + 300
  # The Deployment exists only once the helm-controller's install job ran.
  while not _kubectl("get", "deployment", "--namespace", INGRESS_NAMESPACE, "--selector", "app.kubernetes.io/name=traefik", "--output", "name").strip():
    if time.monotonic() > deadline:
      raise BootstrapError(f"Traefik not installed in {INGRESS_NAMESPACE} after 300s: kubectl --context {CONTEXT} logs --namespace kube-system job/helm-install-platform-ingress")
    time.sleep(3)
  _kubectl("rollout", "status", "deployment", "--selector", "app.kubernetes.io/name=traefik", "--namespace", INGRESS_NAMESPACE, "--timeout", "180s")


def install_profile_policies(forager_dir: Path, log) -> None:
  """The binding policy of each profile (#329): created when missing, never applied over, since
  platform-admins change it through the API."""
  log("creating the binding policies of the profiles …")
  try:
    _kubectl("create", "--filename", str(forager_dir / "deploy" / "profile-policies.yaml"))
  except BootstrapError as error:
    failures = [line for line in str(error).splitlines()[1:] if line.strip() and "AlreadyExists" not in line and "already exists" not in line]
    if failures:
      raise


def install_shared_pg(forager_dir: Path, log) -> None:
  """The shared Postgres compose writes into (#305), in the namespace of the Forager's credentials.
  The admin password is generated once and kept across runs: a new one would lock the Forager out."""
  log("deploying shared-pg (postgres in mode compose) …")
  password = _secret_value(SHARED_PG_NAMESPACE, SHARED_PG_SECRET, "password") or secrets.token_urlsafe(24)
  _apply_secret(SHARED_PG_NAMESPACE, SHARED_PG_SECRET, {"password": password})
  _kubectl("apply", "--filename", str(forager_dir / "deploy" / "shared-pg.yaml"))
  _kubectl("rollout", "status", "statefulset/shared-pg", "--namespace", SHARED_PG_NAMESPACE, "--timeout", "180s")


def seed_templates(root: Path, ref: str, existing: list[dict]) -> list[dict]:
  """Template manifests for platform/templates/*, at ref. The first of each type is the default only
  while no other template of that type is: an admin's `template default` survives a new init."""
  current = {obj["metadata"]["name"]: obj.get("spec") or {} for obj in existing}
  taken = {spec.get("type") for spec in current.values() if spec.get("default")}
  manifests = []
  for definition in sorted((root / SEED_FOLDER).glob("*/template.yaml")):
    data = yaml.safe_load(definition.read_text(encoding="utf-8"))
    name, type_ = data["name"], data["type"]
    spec = {
      "type": type_,
      "source": {"repo": SEED_REPO, "path": (definition.parent / "content").relative_to(root).as_posix(), "ref": ref},
      "parameters": data.get("parameters") or {},
      "copyWithoutRendering": list(data.get("copyWithoutRendering") or []),
      "owner": data["owner"],
    }
    if data.get("description"):
      spec["description"] = data["description"]
    if current.get(name, {}).get("default") or type_ not in taken:
      spec["default"] = True
      taken.add(type_)
    manifests.append({
      "apiVersion": CATALOG_API_VERSION, "kind": "Template",
      "metadata": {"name": name, "namespace": NAMESPACE, "annotations": {"platform.wasp.silvios.me/created-by": "platform-init"}},
      "spec": spec,
    })
  return manifests


def seed_ref(root: Path) -> str:
  """The checkout's commit when it is on the remote; otherwise the last commit of origin/main it
  builds on: the ref is fetched from SEED_REPO on GitHub, where an unpushed commit does not exist."""
  head = _run("git", "-C", str(root), "rev-parse", "HEAD").strip()
  if _run("git", "-C", str(root), "branch", "--remotes", "--contains", head).strip():
    return head
  return _run("git", "-C", str(root), "merge-base", "HEAD", "origin/main").strip()


def install_templates(root: Path, log) -> None:
  """Registers the factory templates at the checkout's commit; applying again only moves the ref."""
  ref = seed_ref(root)
  existing = json.loads(_kubectl("get", "templates.catalog.platform.wasp.silvios.me", "--namespace", NAMESPACE, "--output", "json"))["items"]
  manifests = seed_templates(root, ref, existing)
  log(f"registering {len(manifests)} template(s) at {ref[:7]} …")
  _kubectl("apply", "--filename", "-", input=json.dumps({"apiVersion": "v1", "kind": "List", "items": manifests}))


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
