import os
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
import yaml

from .. import config
from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, print_table, success

app = typer.Typer(help="Environments where releases run.", no_args_is_help=True)

FAILED = {"ProvisioningFailed"}
EXEC_API_VERSION = "client.authentication.k8s.io/v1"


class Profile(str, Enum):
  ephemeral = "ephemeral"
  shared = "shared"


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def remaining(expires_at: str | None, now: datetime | None = None) -> str:
  if not expires_at:
    return "—"
  now = now or datetime.now(timezone.utc)
  seconds = int((datetime.fromisoformat(expires_at.replace("Z", "+00:00")) - now).total_seconds())
  if seconds <= 0:
    return "expired"
  days, rest = divmod(seconds, 86400)
  hours, rest = divmod(rest, 3600)
  minutes = rest // 60
  parts = [f"{days}d" if days else "", f"{hours}h" if hours else "", f"{minutes}m" if minutes and not days else ""]
  return " ".join(part for part in parts if part) or "<1m"


@app.command("create")
def create(
  name: str,
  profile: Annotated[Profile, typer.Option(help="Kind of environment; the platform decides where it runs.")],
  expires: Annotated[str | None, typer.Option(help="Lifetime such as 30m, 12h, 3d or 1w.")] = None,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until the environment is ready.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait with --wait.")] = 600,
  share_with: Annotated[list[str] | None, typer.Option("--share-with", help="Team whose members also use it; repeat for more teams.")] = None,
  output: OutputOption = Format.table,
):
  """Create an environment, private unless shared with teams."""
  client = _client()
  try:
    environment = client.create_environment(name, profile.value, expires, share_with)
    if output == Format.table:
      typer.echo(f"provisioning {name} (profile: {profile.value}) …")
    if wait:
      environment = _wait_ready(client, environment, timeout, quiet=output == Format.json)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(environment)
  elif environment["status"] == "ready":
    success(f"{name} ready")
  else:
    typer.echo(f"{name}: {environment['status']}")


def _wait_ready(client: PlatformClient, environment: dict, timeout: int, quiet: bool) -> dict:
  deadline = time.monotonic() + timeout
  last = None
  while environment["status"] != "ready":
    if environment["status"] != last and not quiet:
      typer.echo(f"  {environment['status']}", err=True)
      last = environment["status"]
    if environment["status"] in FAILED:
      fail(f"{environment['name']}: {environment.get('message') or environment['status']}")
    if time.monotonic() > deadline:
      fail(f"{environment['name']} not ready after {timeout}s (status: {environment['status']})")
    time.sleep(2)
    environment = client.get_environment(environment["name"])
  return save_kubeconfig(environment)


def executable() -> str:
  """This CLI's own path, so kubectl runs the same installation that wrote the kubeconfig (uv run, venvs)."""
  path = Path(sys.argv[0])
  return str(path.resolve()) if path.name == "platform" and path.is_file() else "platform"


def with_executable(data: str) -> str:
  """The API names the credential plugin `platform`; point it at this CLI (ADR 0028)."""
  kubeconfig = yaml.safe_load(data)
  users = (kubeconfig.get("users") or []) if isinstance(kubeconfig, dict) else []
  plugins = [user["user"]["exec"] for user in users if (user.get("user") or {}).get("exec", {}).get("command") == "platform"]
  if not plugins:
    return data
  for plugin in plugins:
    plugin["command"] = executable()
  return yaml.safe_dump(kubeconfig, sort_keys=False)


def save_kubeconfig(environment: dict, suffix: str = "") -> dict:
  """The provider runs inside the cluster and returns the kubeconfig in the API: the CLI writes it locally."""
  data = environment.pop("kubeconfigData", None)
  if data:
    data = with_executable(data)
    path = config.config_dir() / "environments" / f"{environment['name']}{suffix}.kubeconfig"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as file:
      file.write(data)
    environment["kubeconfig"] = str(path)
  return environment


@app.command("list")
def list_(
  all: Annotated[bool, typer.Option("--all", help="Every environment, not only yours and your teams'.")] = False,
  output: OutputOption = Format.table,
):
  """List your environments and the ones shared with your teams."""
  try:
    items = _client().list_environments(all)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(items)
    return
  rows = [
    [item["name"], item["profile"], item["status"], remaining(item.get("expiresAt")), item.get("owner") or "—", ", ".join(item.get("sharedWith") or []) or "—"]
    for item in items
  ]
  print_table(["NAME", "PROFILE", "STATUS", "EXPIRES", "OWNER", "SHARED"], rows)


Team = Annotated[str, typer.Option("--team", help="Team name, such as team-alpha.")]


@app.command("share")
def share(name: str, team: Team, output: OutputOption = Format.table):
  """Share an environment with a team you belong to (owner or platform-admins)."""
  try:
    environment = _client().share_environment(name, team)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(environment)
  else:
    success(f"{name} shared with {team}")


@app.command("unshare")
def unshare(name: str, team: Team, output: OutputOption = Format.table):
  """Stop sharing an environment with a team (owner or platform-admins)."""
  try:
    environment = _client().unshare_environment(name, team)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(environment)
  else:
    success(f"{name} no longer shared with {team}")


@app.command("get")
def get(
  name: str,
  admin: Annotated[bool, typer.Option("--admin", help="Write the vcluster admin kubeconfig instead (platform-admins only).")] = False,
  output: OutputOption = Format.table,
):
  """Show an environment and write your kubeconfig when it is ready."""
  try:
    client = _client()
    environment = client.get_environment(name)
    if admin:
      environment = save_kubeconfig({**environment, **client.admin_kubeconfig(name)}, suffix="-admin")
    else:
      environment = save_kubeconfig(environment)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(environment)
    return
  typer.echo(f"{environment['name']}: {environment['status']}")
  if environment.get("message"):
    typer.echo(f"  {environment['message']}")
  if environment["status"] == "ready" and environment.get("kubeconfig"):
    typer.echo(f"  kubectl --kubeconfig {environment['kubeconfig']} get nodes")


@app.command("credential")
def credential(name: str):
  """Print a short-lived token for the environment, as a kubectl ExecCredential.

  The kubeconfig that `get` writes runs this command: kubectl calls it, never a person.
  """
  try:
    issued = _client().environment_credential(name)
  except ApiError as error:
    fail(str(error))
  print_json({"apiVersion": EXEC_API_VERSION, "kind": "ExecCredential", "status": issued})


@app.command("delete")
def delete(name: str, output: OutputOption = Format.table):
  """Delete an environment."""
  try:
    result = _client().delete_environment(name)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(result)
  else:
    success(f"{name} deleting")


policy_app = typer.Typer(help="The binding policy of an environment: which mode makes each resource there.", no_args_is_help=True)
app.add_typer(policy_app, name="policy")


def print_policy(policy: dict) -> None:
  """Both layers, in the order the Forager resolves them: the first row that matches wins."""
  layers = [("environment", item) for item in policy["provisioners"]] + [("default", item) for item in policy["default"]]
  rows = [
    [layer, item["type"], item.get("class") or "—", item.get("id") or "—", item["mode"], ", ".join(f"{key}={value}" for key, value in sorted((item.get("params") or {}).items())) or "—"]
    for layer, item in layers
  ]
  print_table(["LAYER", "TYPE", "CLASS", "ID", "MODE", "PARAMS"], rows)


@policy_app.command("get")
def policy_get(name: str, output: OutputOption = Format.table):
  """Show the policy of an environment, followed by the platform default."""
  try:
    policy = _client().get_binding_policy(name)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(policy)
  else:
    print_policy(policy)


@policy_app.command("set")
def policy_set(
  name: str,
  file: Annotated[Path, typer.Option("--file", help="YAML with a provisioners list (type, class, id, mode, params); '-' reads stdin.")],
  output: OutputOption = Format.table,
):
  """Replace the policy of an environment (platform-admins). An empty list removes it."""
  try:
    document = yaml.safe_load(sys.stdin.read() if str(file) == "-" else file.read_text())
  except (OSError, yaml.YAMLError) as error:
    fail(f"{file}: {error}")
  provisioners = (document or {}).get("provisioners") if isinstance(document, dict) else None
  if not isinstance(provisioners, list):
    fail(f"{file}: expected a 'provisioners' list")
  try:
    policy = _client().set_binding_policy(name, provisioners)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(policy)
    return
  success(f"{name}: policy set" if policy["provisioners"] else f"{name}: policy removed, the platform default applies")
  print_policy(policy)
