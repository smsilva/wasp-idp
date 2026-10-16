import base64
import contextvars
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import yaml

from .. import config
from .admin_permissions import AdminPermissions
from .tasks import Reporter, Task, emit, note, run_tasks
from .timings import Timings

CLUSTER = "platform-local"
CONTEXT = f"k3d-{CLUSTER}"
NAMESPACE = "platform-system"
API_PORT = "6560"
APP_PORT = "9090"
API_URL = f"http://127.0.0.1:{APP_PORT}"
IMAGE = "platform-api"
AUTH_NAMESPACE = "platform-auth"
# Language of the sign-in pages written to a config that names none (#537, #545 makes it an init setting).
DEFAULT_LOCALE = "en"
KEYCLOAK_PORT = "8180"
# Read by the Platform API for `platform status` (platform_api.capabilities, ADR 0039).
IDENTITY_PROVIDERS_ANNOTATION = "platform.wasp.silvios.me/identity-providers"
# Must match KC_HOSTNAME in platform/keycloak/deploy/keycloak.yaml: it is the `iss` of every token.
KEYCLOAK_URL = f"http://localhost:{KEYCLOAK_PORT}"
ISSUER = f"{KEYCLOAK_URL}/realms/platform"
CLI_CLIENT_ID = "platform-cli"
# Test client and users of scripts/test/cli-smoke and cli-e2e (#179, realm-smoke.yaml): local target only.
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
# Environments in a cloud account (#436, ADR 0032): Crossplane and the provider that writes its resources.
# The base credential is copied to CROSSPLANE_NAMESPACE under the same name, in the INI form Crossplane reads.
CROSSPLANE_NAMESPACE = "crossplane-system"
CROSSPLANE_PROVIDER_IMAGE = "crossplane-aws-provider"
CROSSPLANE_PROVIDER_PACKAGE = "upbound-provider-aws-ec2"
# Cloud accounts (ADR 0029): the base credential the aws_account controller assumes roles from.
AWS_PROVIDER_IMAGE = "aws-account-provider"
AWS_BASE_SECRET = "aws-base-credential"

SCM_PROVIDER_IMAGE = "scm-github-provider"
# Workload Instances (ADR 0033): applies each WorkloadRevision in the vcluster of its Environment.
WORKLOAD_PROVIDER_IMAGE = "workload-provider"
FORAGER_PROVIDER_IMAGE = "forager-provider"
# OCI registries (ADR 0037): checks that each one answers; pull credentials come later (#367).
REGISTRY_PROVIDER_IMAGE = "registry-provider"
# The shared instance of postgres in mode compose and its admin password (#305).
SHARED_PG_NAMESPACE = "platform-resources"
SHARED_PG_SECRET = "shared-pg-admin"
# Factory templates (ADR 0024): read from this public repo, so no credential is needed.
SEED_REPO = "https://github.com/smsilva/wasp-idp"
SEED_FOLDER = Path("platform") / "templates"
CATALOG_API_VERSION = "catalog.platform.wasp.silvios.me/v1alpha1"
CHART_DIR = Path("platform") / "chart" / "platform-control-plane"
CHART_NAME = "platform-control-plane"


class BootstrapError(Exception):
  pass


def repo_root() -> Path:
  """The wasp-idp checkout: init applies CRDs, manifests and scripts versioned there."""
  root = Path(os.environ.get("PLATFORM_REPO") or Path(__file__).resolve().parents[4])
  if not (root / "platform" / "crds").is_dir():
    raise BootstrapError(f"wasp-idp checkout not found at {root}: install the CLI editable from the repo or set PLATFORM_REPO")
  return root


# The steps of init run side by side (#444): the first one to fail calls stop(), which ends the commands
# the others are running, and every later command or wait refuses to start.
_processes: set[subprocess.Popen] = set()
_processes_lock = threading.Lock()
_stopping = threading.Event()


class Stopped(BootstrapError):
  pass


def stop() -> None:
  _stopping.set()
  with _processes_lock:
    for process in _processes:
      process.terminate()


def _pause(seconds: float) -> None:
  if _stopping.wait(seconds):
    raise Stopped("stopped: another step failed")


def _drain(stream, lines: list[str], secret: bool = False) -> None:
  """Each line goes to the step's log as it comes (#458), and is kept for the result or the error."""
  for line in stream:
    lines.append(line)
    if not secret:
      emit("output", line.rstrip("\n"))


def _feed(stream, text: str) -> None:
  try:
    stream.write(text)
    stream.close()
  except BrokenPipeError:
    pass


def _run(*command: str, input: str | None = None, secret: bool = False) -> str:
  """Returns stdout; stdout and stderr both reach the step's log, read side by side so neither pipe fills.
  secret: the output holds a credential, so the log gets only the command and its exit code. The input
  never reaches the log: it carries Secrets."""
  if _stopping.is_set():
    raise Stopped("stopped: another step failed")
  emit("command", command)
  try:
    process = subprocess.Popen(command, text=True, stdin=subprocess.PIPE if input is not None else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  except FileNotFoundError as error:
    raise BootstrapError(f"'{command[0]}' not found in PATH") from error
  with _processes_lock:
    _processes.add(process)
  stdout: list[str] = []
  stderr: list[str] = []
  try:
    # The context carries the current step into the reader thread; stdin has its own, as communicate() does.
    threads = [threading.Thread(target=contextvars.copy_context().run, args=(_drain, process.stderr, stderr, secret))]
    if input is not None:
      threads.append(threading.Thread(target=_feed, args=(process.stdin, input)))
    for thread in threads:
      thread.start()
    _drain(process.stdout, stdout, secret)
    for thread in threads:
      thread.join()
    process.wait()
  finally:
    with _processes_lock:
      _processes.discard(process)
  emit("exited", process.returncode)
  if process.returncode != 0:
    if _stopping.is_set():
      raise Stopped("stopped: another step failed")
    raise BootstrapError(f"{' '.join(command[:3])} … failed:\n{(''.join(stderr) or ''.join(stdout)).strip()}")
  return "".join(stdout)


def _kubectl(*args: str, input: str | None = None, secret: bool = False) -> str:
  return _run("kubectl", "--context", CONTEXT, *args, input=input, secret=secret)


def cluster_exists() -> bool:
  names = _run("k3d", "cluster", "list", "--no-headers").split()
  return CLUSTER in names


def _ensure_port(ports: str) -> None:
  """Clusters created by an older init lack newer mappings; k3d can add them to the load balancer."""
  clusters = json.loads(_run("k3d", "cluster", "list", CLUSTER, "--output", "json"))
  mapped = json.dumps(clusters[0].get("nodes", []))
  if f'"HostPort": "{ports.split("-")[0]}"' in mapped:
    return
  note(f"adding port {ports} to cluster {CLUSTER} …")
  _run("k3d", "cluster", "edit", CLUSTER, "--port-add", f"127.0.0.1:{ports}:{ports}@loadbalancer")


def _build(name: str, context: Path, dockerfile: Path | None = None) -> str:
  """Build and tag by image id: an unchanged build keeps the tag, so its import and rollout are skipped.
  dockerfile: when the context is wider than the project folder (a project with path dependencies)."""
  file = ["--file", str(dockerfile)] if dockerfile else []
  # Without provenance: its attestation changes the image id on every build (containerd image store),
  # so an unchanged project would get a new tag and a rollout on every init.
  _run("docker", "build", "--quiet", "--provenance=false", *file, "--tag", f"{name}:dev", str(context))
  image_id = _run("docker", "image", "inspect", "--format", "{{.Id}}", f"{name}:dev").strip()
  image = f"{name}:{image_id.removeprefix('sha256:')[:12]}"
  _run("docker", "tag", f"{name}:dev", image)
  return image


def _cluster_images() -> set[str]:
  """Images present on every node of platform-local that runs pods, as docker.io/library/<name>:<tag>."""
  nodes = [
    node["name"] for node in json.loads(_run("k3d", "node", "list", "--output", "json"))
    if node.get("runtimeLabels", {}).get("k3d.cluster") == CLUSTER and node.get("role") in ("server", "agent")
  ]
  listed = [set(_run("docker", "exec", node, "ctr", "--namespace", "k8s.io", "images", "list", "--quiet").split()) for node in nodes]
  return set.intersection(*listed) if listed else set()


def build_images(builds: dict[str, tuple[Path, Path | None]]) -> dict[str, str]:
  """Builds every image in parallel; it needs no cluster, so it starts with init. Returns name -> image."""
  with ThreadPoolExecutor(max_workers=len(builds)) as pool:
    # Each build copies the context, so its commands reach the log of the "build images" step.
    futures = {name: pool.submit(contextvars.copy_context().run, _build, name, context, dockerfile) for name, (context, dockerfile) in builds.items()}
    try:
      return {name: future.result() for name, future in futures.items()}
    except BootstrapError:
      for future in futures.values():
        future.cancel()
      raise


def import_images(images: dict[str, str]) -> None:
  """Imports only the images the cluster lacks, in one k3d call: each `k3d image import` costs ~20 s
  even for a small image (#443)."""
  present = _cluster_images()
  missing = [image for image in images.values() if f"docker.io/library/{image}" not in present]
  if not missing:
    note("images already in the cluster, nothing to import")
    return
  note(f"importing {len(missing)} image(s) into {CLUSTER} …")
  _run("k3d", "image", "import", *missing, "--cluster", CLUSTER)


def _render(root: Path, template_path: str, set_values: dict[str, str] | None = None) -> str:
  """Renders one template of the control-plane chart, the same object `_kubectl("apply", ...)` used to
  read straight from a YAML file. `set_values` mirrors `--set key=value` (e.g. an image's tag)."""
  args = ["helm", "template", CHART_NAME, str(root / CHART_DIR), "--show-only", template_path]
  for key, value in (set_values or {}).items():
    args.extend(["--set", f"{key}={value}"])
  return _run(*args)


# Maps the image constant (IMAGE, PROVIDER_IMAGE, ...) each _deploy call already passes to the chart's
# values key and template path, so this dict is the single place that pairing lives.
CHART_TEMPLATES = {
  IMAGE: ("templates/api/platform-api.yaml", "images.api"),
  PROVIDER_IMAGE: ("templates/providers/local-vcluster-provider.yaml", "images.localVclusterProvider"),
  SCM_PROVIDER_IMAGE: ("templates/providers/scm-github-provider.yaml", "images.scmGithubProvider"),
  WORKLOAD_PROVIDER_IMAGE: ("templates/providers/workload-provider.yaml", "images.workloadProvider"),
  FORAGER_PROVIDER_IMAGE: ("templates/providers/forager-provider.yaml", "images.foragerProvider"),
  REGISTRY_PROVIDER_IMAGE: ("templates/providers/registry-provider.yaml", "images.registryProvider"),
  AWS_PROVIDER_IMAGE: ("templates/providers/aws-account-provider.yaml", "images.awsAccountProvider"),
  CROSSPLANE_PROVIDER_IMAGE: ("templates/providers/crossplane-aws-provider.yaml", "images.crossplaneAwsProvider"),
}


def _deploy(root: Path, name: str, image: str) -> None:
  template_path, values_key = CHART_TEMPLATES[name]
  set_values = {f"{values_key}.tag": image.split(":", 1)[1]}
  if name == AWS_PROVIDER_IMAGE:
    set_values["providers.awsAccount.enabled"] = "true"
  if name == CROSSPLANE_PROVIDER_IMAGE:
    set_values["providers.crossplaneAws.enabled"] = "true"
  manifest = _render(root, template_path, set_values)
  _kubectl("apply", "--filename", "-", input=manifest)


def _rollout(deployment: str, namespace: str = NAMESPACE) -> None:
  _kubectl("rollout", "status", f"deployment/{deployment}", "--namespace", namespace, "--timeout", "180s")


def _secret_value(namespace: str, name: str, key: str) -> str | None:
  try:
    encoded = _kubectl("get", "secret", name, "--namespace", namespace, "--output", f"jsonpath={{.data.{key}}}", secret=True)
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


def render_realm(realm: dict, google: bool, admins: list[str], smoke: dict | None = None) -> dict:
  """Drop the Google identity provider without credentials; the bootstrap-admin mapper becomes one mapper
  per --admin e-mail (#462), none without --admin. With smoke (realm-smoke.yaml, local target only), add
  the test client and users of #179."""
  realm = dict(realm)
  if smoke:
    realm["clients"] = [*realm.get("clients", []), *smoke.get("clients", [])]
    realm["users"] = [*realm.get("users", []), *smoke.get("users", [])]
  if not google:
    realm.pop("identityProviders", None)
    realm.pop("identityProviderMappers", None)
  else:
    mappers = realm.get("identityProviderMappers", [])
    template = next(m for m in mappers if m["name"] == "bootstrap-admin")
    realm["identityProviderMappers"] = [m for m in mappers if m["name"] != "bootstrap-admin"] + [
      {**template, "name": f"bootstrap-admin-{email}", "config": {**template["config"], "claims": json.dumps([{"key": "email", "value": email}])}}
      for email in admins
    ]
  return realm


def deploy_keycloak(root: Path, admin_emails: list[str]) -> dict:
  keycloak_dir = root / "platform" / "keycloak"
  _kubectl("apply", "--filename", "-", input=_render(root, "templates/keycloak/keycloak.yaml"))

  # The bootstrap admin password is generated once and kept: Keycloak only reads it on first start.
  if not _secret_value(AUTH_NAMESPACE, "keycloak-admin", "password"):
    _apply_secret(AUTH_NAMESPACE, "keycloak-admin", {"username": "admin", "password": secrets.token_urlsafe(24)})

  # --admin is remembered in the Secret (comma-separated), so a later `init` without it keeps the bootstrap admins.
  admin_emails = admin_emails or remembered_admins()
  client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
  client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
  if not (client_id and client_secret):
    client_id = _secret_value(AUTH_NAMESPACE, "keycloak-google", "GOOGLE_CLIENT_ID") or ""
    client_secret = _secret_value(AUTH_NAMESPACE, "keycloak-google", "GOOGLE_CLIENT_SECRET") or ""
  google = bool(client_id and client_secret)
  if not google:
    note("warning: GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET not set — realm without the Google identity provider")
  _apply_secret(AUTH_NAMESPACE, "keycloak-google", {
    "GOOGLE_CLIENT_ID": client_id,
    "GOOGLE_CLIENT_SECRET": client_secret,
    "PLATFORM_ADMIN_EMAIL": ",".join(admin_emails),
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

  realm = render_realm(yaml.safe_load((keycloak_dir / "realm-platform.yaml").read_text()), google, admin_emails, smoke)
  configmap = {
    "apiVersion": "v1", "kind": "ConfigMap",
    "metadata": {"name": "keycloak-realm", "namespace": AUTH_NAMESPACE},
    "data": {"realm-platform.yaml": yaml.safe_dump(realm, sort_keys=False)},
  }
  _kubectl("apply", "--filename", "-", input=json.dumps(configmap))

  _apply_theme(keycloak_dir / "theme" / "platform")
  _kubectl("rollout", "status", "deployment/keycloak", "--namespace", AUTH_NAMESPACE, "--timeout", "300s")
  return {"issuer": ISSUER, "google": google, "admins": admin_emails}


def import_realm(root: Path, google: bool) -> None:
  _kubectl("delete", "job", "keycloak-realm-import", "--namespace", AUTH_NAMESPACE, "--ignore-not-found")
  _kubectl("apply", "--filename", "-", input=_render(root, "templates/keycloak/realm-import.yaml"))
  try:
    _kubectl("wait", "job/keycloak-realm-import", "--namespace", AUTH_NAMESPACE, "--for", "condition=Complete", "--timeout", "300s")
  except Stopped:
    raise
  except BootstrapError as error:
    logs = _kubectl("logs", "job/keycloak-realm-import", "--namespace", AUTH_NAMESPACE, "--tail", "30")
    raise BootstrapError(f"realm import did not complete:\n{logs}") from error
  wait_issuer(ISSUER)
  # What `platform status` shows for identity (ADR 0039): the API reads Deployments, never this Secret.
  # On the Deployment, not its template: changing it restarts nothing.
  _kubectl("annotate", "deployment", "keycloak", "--namespace", AUTH_NAMESPACE, "--overwrite", f"{IDENTITY_PROVIDERS_ANNOTATION}={'google' if google else ''}")


def apply_admin_permissions(admins: list[str]) -> None:
  try:
    AdminPermissions(
      KEYCLOAK_URL,
      _secret_value(AUTH_NAMESPACE, "keycloak-admin", "username"),
      _secret_value(AUTH_NAMESPACE, "keycloak-admin", "password"),
    ).apply(note, admins)
  except httpx.HTTPError as error:
    raise BootstrapError(f"admin permissions of {API_ADMIN_SECRET} not applied: {error}") from error


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
    _pause(2)


def aws_base_credential(profile: str) -> dict:
  """The profile's credential as the controller's environment; SSO and assumed roles carry an Expiration."""
  exported = json.loads(_run("aws", "configure", "export-credentials", "--profile", profile, "--format", "process", secret=True))
  values = {"AWS_ACCESS_KEY_ID": exported["AccessKeyId"], "AWS_SECRET_ACCESS_KEY": exported["SecretAccessKey"]}
  if exported.get("SessionToken"):
    values["AWS_SESSION_TOKEN"] = exported["SessionToken"]
  return {"values": values, "expiration": exported.get("Expiration")}


def store_aws_credential(aws_profile: str | None) -> tuple[dict, str | None]:
  """With --aws-profile, store the base credential. Returns the stored one (now or by an earlier init)
  and its expiration; without one, cloud accounts stay NoProviderForCapability."""
  expiration = None
  if aws_profile:
    credential = aws_base_credential(aws_profile)
    expiration = credential["expiration"]
    # Replaced whole: a long-lived key must not keep the session token of an earlier temporary one.
    _kubectl("delete", "secret", AWS_BASE_SECRET, "--namespace", NAMESPACE, "--ignore-not-found")
    _apply_secret(NAMESPACE, AWS_BASE_SECRET, credential["values"])
    if expiration:
      note(f"warning: the credential of profile {aws_profile} expires at {expiration}: run init again after that, or use a dedicated IAM user")
  values = {key: _secret_value(NAMESPACE, AWS_BASE_SECRET, key) for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")}
  return (values if values["AWS_ACCESS_KEY_ID"] else {}), expiration


def install_aws_account(root: Path, provider_dir: Path, aws_profile: str | None) -> dict:
  """The aws_account controller, with the stored base credential as its environment. Its image is built
  here, not with the others: it exists only when a credential is stored."""
  values, expiration = store_aws_credential(aws_profile)
  if not values:
    return {"cloud_account": False, "values": {}}
  image = _build(AWS_PROVIDER_IMAGE, provider_dir)
  import_images({AWS_PROVIDER_IMAGE: image})
  _deploy(root, AWS_PROVIDER_IMAGE, image)
  # The credential reaches the pod as environment: a new one needs a new pod, an unchanged one keeps it.
  digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:16]
  patch = {"spec": {"template": {"metadata": {"annotations": {"platform.wasp.silvios.me/credential": digest}}}}}
  _kubectl("patch", "deployment", AWS_PROVIDER_IMAGE, "--namespace", NAMESPACE, "--type", "merge", "--patch", json.dumps(patch))
  _rollout(AWS_PROVIDER_IMAGE)
  return {"cloud_account": True, "aws_base_expires": expiration, "values": values}


def crossplane_credential(values: dict[str, str | None]) -> str:
  """The base credential as the `creds` key of a Crossplane ProviderConfig (an AWS shared credentials file)."""
  lines = ["[default]", f"aws_access_key_id = {values['AWS_ACCESS_KEY_ID']}", f"aws_secret_access_key = {values['AWS_SECRET_ACCESS_KEY']}"]
  if values.get("AWS_SESSION_TOKEN"):
    lines.append(f"aws_session_token = {values['AWS_SESSION_TOKEN']}")
  return "\n".join(lines) + "\n"


def crossplane_installed() -> bool:
  return bool(_kubectl("get", "helmchart", "crossplane", "--namespace", "kube-system", "--ignore-not-found", "--output", "name").strip())


def remembered() -> dict:
  """What an earlier init kept in the cluster (#462), for the settings table; nothing without a cluster.
  The AWS profile is not kept, only its credential."""
  if not shutil.which("k3d") or not cluster_exists():
    return {}
  return {
    "admins": remembered_admins(),
    "with_crossplane": crossplane_installed() or None,
  }


def remembered_admins() -> list[str]:
  return [email for email in (_secret_value(AUTH_NAMESPACE, "keycloak-google", "PLATFORM_ADMIN_EMAIL") or "").split(",") if email]


def aws_credential_stored() -> bool:
  return bool(shutil.which("k3d")) and cluster_exists() and bool(_secret_value(NAMESPACE, AWS_BASE_SECRET, "AWS_ACCESS_KEY_ID"))


def planned_steps(aws_profile: str | None, with_crossplane: bool) -> list[str]:
  """The steps init would run (#462, --dry-run), in their declared order. aws-account-provider and
  crossplane run always but do nothing without a credential: they are listed only when they install."""
  aws = bool(aws_profile) or aws_credential_stored()
  if with_crossplane and not aws:
    raise BootstrapError("--with-crossplane needs the base credential of cloud accounts: add --aws-profile <profile>")
  skipped = {"aws-account-provider"} if not aws else set()
  if not with_crossplane:
    skipped.add("crossplane")
  return [task.name for task in init_tasks(repo_root(), [], aws_profile, with_crossplane) if task.name not in skipped]


def wants_crossplane(with_crossplane: bool, aws_values: dict) -> bool:
  """With --with-crossplane, or installed by an earlier init. Without it, environments in a cloud account
  stay NoProviderForCapability."""
  if with_crossplane and not aws_values:
    raise BootstrapError("--with-crossplane needs the base credential of cloud accounts: add --aws-profile <profile>")
  return bool(aws_values) and (with_crossplane or crossplane_installed())


def _wait_for(description: str, check, timeout: int, hint: str) -> None:
  deadline = time.monotonic() + timeout
  while not check():
    if time.monotonic() > deadline:
      raise BootstrapError(f"{description} not there after {timeout}s: {hint}")
    _pause(3)


def install_crossplane(root: Path, provider_dir: Path, values: dict, with_crossplane: bool) -> dict:
  """Crossplane, provider-aws-ec2, the base credential in crossplane-system and the crossplane_aws provider.
  Its image is built here, like the aws_account one: it exists only with Crossplane."""
  if not wants_crossplane(with_crossplane, values):
    return {"crossplane": False}
  image = _build(CROSSPLANE_PROVIDER_IMAGE, provider_dir)
  import_images({CROSSPLANE_PROVIDER_IMAGE: image})
  _kubectl("apply", "--filename", "-", input=_render(root, "templates/providers/crossplane.yaml", {"providers.crossplaneAws.enabled": "true"}))
  # The CRDs exist only once the helm-controller's install job ran.
  _wait_for(
    "Crossplane", lambda: bool(_kubectl("get", "crd", "providers.pkg.crossplane.io", "--ignore-not-found", "--output", "name").strip()), 300,
    f"kubectl --context {CONTEXT} logs --namespace kube-system job/helm-install-crossplane",
  )
  _kubectl("wait", "crd", "providers.pkg.crossplane.io", "--for", "condition=Established", "--timeout", "60s")
  _kubectl("rollout", "status", "deployment/crossplane", "--namespace", CROSSPLANE_NAMESPACE, "--timeout", "180s")
  # Replaced whole, as in platform-system: a long-lived key must not keep the session token of a temporary one.
  _kubectl("delete", "secret", AWS_BASE_SECRET, "--namespace", CROSSPLANE_NAMESPACE, "--ignore-not-found")
  _apply_secret(CROSSPLANE_NAMESPACE, AWS_BASE_SECRET, {"creds": crossplane_credential(values)})
  note("installing the Crossplane provider for AWS EC2 (pulls its package, a few minutes the first time) …")
  _kubectl("apply", "--filename", "-", input=_render(root, "templates/providers/provider-aws-ec2.yaml", {"providers.crossplaneAws.enabled": "true"}))
  _kubectl("wait", f"provider.pkg.crossplane.io/{CROSSPLANE_PROVIDER_PACKAGE}", "--for", "condition=Healthy", "--timeout", "600s")
  _kubectl("wait", "crd", "vpcs.ec2.aws.upbound.io", "providerconfigs.aws.upbound.io", "--for", "condition=Established", "--timeout", "120s")
  _deploy(root, CROSSPLANE_PROVIDER_IMAGE, image)
  _rollout(CROSSPLANE_PROVIDER_IMAGE)
  return {"crossplane": True}


def ensure_cluster(root: Path) -> None:
  if cluster_exists():
    note(f"cluster {CLUSTER} already exists, reusing it")
  else:
    _run(
      str(root / "scripts" / "cluster-zero" / "cluster-create"),
      "--name", CLUSTER,
      "--api-port", API_PORT,
      "--app-port", f"127.0.0.1:{APP_PORT}",
      "--extra-port", f"127.0.0.1:{KEYCLOAK_PORT}:{KEYCLOAK_PORT}",
      "--extra-port", f"127.0.0.1:{ENV_PORTS}:{ENV_PORTS}",
      "--extra-port", f"127.0.0.1:{INGRESS_PORT}:{INGRESS_PORT}",
    )
  _ensure_port(KEYCLOAK_PORT)
  _ensure_port(ENV_PORTS)
  _ensure_port(INGRESS_PORT)


def apply_crds(root: Path) -> None:
  """The CRDs and the namespaces every later step writes into, so no step waits on another's manifest."""
  _kubectl("apply", "--filename", str(root / "platform" / "crds"))
  _kubectl("wait", "crd", "--all", "--for", "condition=Established", "--timeout", "60s")
  for namespace in (NAMESPACE, AUTH_NAMESPACE, SHARED_PG_NAMESPACE):
    _ensure_namespace(namespace)


def deploy_provider(root: Path, name: str, image: str) -> None:
  _deploy(root, name, image)
  _rollout(name)


def init_tasks(root: Path, admin_emails: list[str], aws_profile: str | None, with_crossplane: bool = False) -> list[Task]:
  """The steps of init and what each one needs (#444). Providers need only the CRDs and their image,
  never Keycloak or the API; the API needs Keycloak's realm (its admin client) and its image."""
  api_dir = root / "platform" / "api"
  providers = root / "platform" / "providers"
  vcluster_dir, forager_dir = providers / "local_vcluster", providers / "forager"
  # Context platform/ for the API and scm_github: they depend on platform/libs/templates and platform/libs/score by path.
  builds = {
    IMAGE: (api_dir.parent, api_dir / "Dockerfile"),
    PROVIDER_IMAGE: (vcluster_dir, None),
    SCM_PROVIDER_IMAGE: (providers.parent, providers / "scm_github" / "Dockerfile"),
    WORKLOAD_PROVIDER_IMAGE: (providers / "workload", None),
    FORAGER_PROVIDER_IMAGE: (forager_dir, None),
    REGISTRY_PROVIDER_IMAGE: (providers / "registry", None),
  }
  provider_manifests = {
    PROVIDER_IMAGE: (vcluster_dir, "local-vcluster-provider.yaml"),
    SCM_PROVIDER_IMAGE: (providers / "scm_github", "scm-github-provider.yaml"),
    WORKLOAD_PROVIDER_IMAGE: (providers / "workload", "workload-provider.yaml"),
    FORAGER_PROVIDER_IMAGE: (forager_dir, "forager-provider.yaml"),
    REGISTRY_PROVIDER_IMAGE: (providers / "registry", "registry-provider.yaml"),
  }

  def api(results):
    _deploy(root, IMAGE, results["build images"][IMAGE])
    _rollout("platform-api")
    wait_healthy(API_URL)

  def provider(name, directory, manifest):
    return Task(name, lambda results: deploy_provider(root, name, results["build images"][name]), needs=("CRDs", "import images"))

  return [
    Task("cluster", lambda results: ensure_cluster(root)),
    Task("build images", lambda results: build_images(builds)),
    Task("CRDs", lambda results: apply_crds(root), needs=("cluster",)),
    Task("import images", lambda results: import_images(results["build images"]), needs=("cluster", "build images")),
    Task("keycloak", lambda results: deploy_keycloak(root, admin_emails), needs=("CRDs",)),
    Task("keycloak realm", lambda results: import_realm(root, results["keycloak"]["google"]), needs=("keycloak",)),
    Task("keycloak admin permissions", lambda results: apply_admin_permissions(results["keycloak"]["admins"]), needs=("keycloak realm",)),
    Task(IMAGE, api, needs=("keycloak admin permissions", "import images")),
    *(provider(name, directory, manifest) for name, (directory, manifest) in provider_manifests.items()),
    # The pods of every environment as the vcluster syncs them (ADR 0041): its users are cluster-admin inside.
    Task("pod policy", lambda results: _kubectl("apply", "--filename", "-", input=_render(root, "templates/providers/pod-security.yaml")), needs=("CRDs",)),
    Task("traefik", lambda results: install_ingress(root), needs=("CRDs",)),
    Task("shared-pg", lambda results: install_shared_pg(root), needs=("CRDs",)),
    Task("profile policies", lambda results: install_profile_policies(root), needs=("CRDs",)),
    Task("prometheus", lambda results: install_observability(root), needs=("CRDs",)),
    Task("templates", lambda results: install_templates(root), needs=("CRDs",)),
    # After the shared import: two `k3d image import` at once would race for the same tools node.
    Task("aws-account-provider", lambda results: install_aws_account(root, providers / "aws_account", aws_profile), needs=("CRDs", "import images")),
    # After aws-account-provider: it stores the base credential and imports its own image (one k3d import at a time).
    Task("crossplane", lambda results: install_crossplane(root, providers / "crossplane_aws", results["aws-account-provider"]["values"], with_crossplane), needs=("aws-account-provider",)),
  ]


def install(admin_emails: list[str] | None = None, reporter: Reporter | None = None, aws_profile: str | None = None, with_crossplane: bool = False, timings: Timings | None = None) -> dict:
  """timings: passed by the caller so the steps run so far can be shown when init fails."""
  reporter = reporter or Reporter()
  timings = timings or Timings()
  for tool in ("docker", "k3d", "kubectl", "helm", *(("aws",) if aws_profile else ())):
    if not shutil.which(tool):
      raise BootstrapError(f"'{tool}' not found in PATH")
  root = repo_root()
  _stopping.clear()
  results = run_tasks(init_tasks(root, admin_emails or [], aws_profile, with_crossplane), reporter, timings, on_failure=stop)

  identity = results["keycloak"]
  path = config.save(cli_config(config.load(), identity["issuer"]))
  return {
    "target": "local", "cluster": CLUSTER, "api_url": API_URL, "image": results["build images"][IMAGE], "config": str(path),
    **identity, **{key: value for key, value in results["aws-account-provider"].items() if key != "values"},
    **results["crossplane"], "timings": timings.as_dict(),
  }


def cli_config(current: dict, issuer: str) -> dict:
  """The CLI config after init: the control plane it points at, and the sign-in pages in English unless the
  config already names a locale (#537)."""
  return {
    "locale": DEFAULT_LOCALE, **current,
    "target": "local", "api_url": API_URL, "context": CONTEXT, "issuer": issuer, "client_id": CLI_CLIENT_ID,
  }


def install_ingress(root: Path) -> None:
  """The shared Traefik of the environments (ADR 0036), through the helm-controller of k3s."""
  _kubectl("apply", "--filename", "-", input=_render(root, "templates/providers/traefik.yaml"))
  deadline = time.monotonic() + 300
  # The Deployment exists only once the helm-controller's install job ran.
  while not _kubectl("get", "deployment", "--namespace", INGRESS_NAMESPACE, "--selector", "app.kubernetes.io/name=traefik", "--output", "name").strip():
    if time.monotonic() > deadline:
      raise BootstrapError(f"Traefik not installed in {INGRESS_NAMESPACE} after 300s: kubectl --context {CONTEXT} logs --namespace kube-system job/helm-install-platform-ingress")
    _pause(3)
  _kubectl("rollout", "status", "deployment", "--selector", "app.kubernetes.io/name=traefik", "--namespace", INGRESS_NAMESPACE, "--timeout", "180s")


def install_observability(root: Path) -> None:
  """The Prometheus of the observability subsystem (ADR 0040): an upstream image, nothing to build.
  The hash of the manifest goes on the pod template, so a changed scrape config rolls the pod."""
  manifest = _render(root, "templates/observability/prometheus.yaml")
  checksum = hashlib.sha256(manifest.encode()).hexdigest()[:12]
  _kubectl("apply", "--filename", "-", input=manifest.replace("config-hash: dev", f"config-hash: {checksum}"))
  _kubectl("rollout", "status", "deployment/prometheus", "--namespace", NAMESPACE, "--timeout", "180s")


def install_profile_policies(root: Path) -> None:
  """The binding policy of each profile (#329): created when missing, never applied over, since
  platform-admins change it through the API."""
  try:
    _kubectl("create", "--filename", "-", input=_render(root, "templates/providers/profile-policies.yaml"))
  except BootstrapError as error:
    failures = [line for line in str(error).splitlines()[1:] if line.strip() and "AlreadyExists" not in line and "already exists" not in line]
    if failures:
      raise


def install_shared_pg(root: Path) -> None:
  """The shared Postgres compose writes into (#305), in the namespace of the Forager's credentials.
  The admin password is generated once and kept across runs: a new one would lock the Forager out."""
  password = _secret_value(SHARED_PG_NAMESPACE, SHARED_PG_SECRET, "password") or secrets.token_urlsafe(24)
  _apply_secret(SHARED_PG_NAMESPACE, SHARED_PG_SECRET, {"password": password})
  _kubectl("apply", "--filename", "-", input=_render(root, "templates/providers/shared-pg.yaml"))
  _kubectl("rollout", "status", "statefulset/shared-pg", "--namespace", SHARED_PG_NAMESPACE, "--timeout", "180s")


def seed_templates(root: Path, ref: str, existing: list[dict]) -> list[dict]:
  """Template manifests for platform/templates/*, at ref. The one marked `default: true` in its
  template.yaml (else the first in name order) is the default of its type only while no other template
  of that type is: an admin's `template default` survives a new init."""
  current = {obj["metadata"]["name"]: obj.get("spec") or {} for obj in existing}
  taken = {spec.get("type") for spec in current.values() if spec.get("default")}
  definitions = [(definition, yaml.safe_load(definition.read_text(encoding="utf-8"))) for definition in sorted((root / SEED_FOLDER).glob("*/template.yaml"))]
  preferred = {}
  for _, data in sorted(definitions, key=lambda item: not item[1].get("default")):
    preferred.setdefault(data["type"], data["name"])
  manifests = []
  for definition, data in definitions:
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
    if current.get(name, {}).get("default") or (type_ not in taken and preferred[type_] == name):
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


def install_templates(root: Path) -> None:
  """Registers the factory templates at the checkout's commit; applying again only moves the ref."""
  ref = seed_ref(root)
  existing = json.loads(_kubectl("get", "templates.catalog.platform.wasp.silvios.me", "--namespace", NAMESPACE, "--output", "json"))["items"]
  manifests = seed_templates(root, ref, existing)
  note(f"registering {len(manifests)} template(s) at {ref[:7]} …")
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
    _pause(2)
