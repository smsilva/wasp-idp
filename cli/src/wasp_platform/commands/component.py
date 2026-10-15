"""platform catalog component: create a repo through the golden path, and read the component index (#204).

A component lives in its repo's catalog-info.yaml (ADR 0023): the platform creates the repo and
indexes it; changing a component is a pull request in its repo.
"""
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

from .. import config
from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, drop_empty, examples, fail, next_steps, print_data, print_table, success
from .environment import remaining
from .template import _params

app = typer.Typer(help="Components: repos created through the golden path, and the index.", no_args_is_help=True)
creation_app = typer.Typer(help="Creation requests: follow one, or free the name of a stopped one.", no_args_is_help=True)
app.add_typer(creation_app, name="creation")

# Ready=False with these reasons does not heal by waiting: --wait stops at once.
FINAL = {"RepoAlreadyExists", "RepoGone", "ComponentExists", "GitHubRejected", "ConnectionNotFound", "ConnectionNotReady", "CredentialMissing"}
# Of those, the ones that stop the creation for good: it holds the name until replaced or deleted (#452).
STOPPED = {"RepoAlreadyExists", "RepoGone", "ComponentExists", "GitHubRejected"}
# Protected=False with this reason is a warning: main is unprotected (a private repo on GitHub Free), the
# creation still ends Ready.
UNPROTECTED = "ProtectionUnavailable"
# The only SCM vendor is GitHub (#199): repo is <org>/<repo> on github.com.
GIT_URLS = {"ssh": "git@github.com:{repo}.git", "https": "https://github.com/{repo}.git"}
REPO = re.compile(r"[\w.-]+/[\w.-]+")
# Files the summary names when the template generated them.
ANNOUNCED = ("docs/prd.md", "AGENTS.md")


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


def age(since: str | None) -> str:
  if not since:
    return "—"
  seconds = int((utcnow() - datetime.fromisoformat(since.replace("Z", "+00:00"))).total_seconds())
  days, rest = divmod(max(seconds, 0), 86400)
  hours, rest = divmod(rest, 3600)
  minutes = rest // 60
  return f"{days}d" if days else f"{hours}h" if hours else f"{minutes}m" if minutes else "<1m"


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def _prd(value: str | None) -> str | None:
  if value is None:
    return None
  if value == "-":
    return sys.stdin.read()
  try:
    return Path(value).read_text(encoding="utf-8")
  except OSError as error:
    fail(f"--prd {value}: {error.strerror}")


def _ready(creation: dict) -> dict:
  return next((item for item in creation.get("conditions") or [] if item["type"] == "Ready"), {})


def _mark(condition: dict, pending: str) -> str:
  if condition["status"] == "True":
    return "✓"
  return "⚠" if condition.get("reason") == UNPROTECTED else pending


def warnings(creation: dict) -> list[str]:
  """What the creation could not do but did not fail on."""
  return [item.get("message") or item["reason"] for item in creation.get("conditions") or [] if item["status"] != "True" and item.get("reason") == UNPROTECTED]


def summary(creation: dict, type_: str | None) -> list[str]:
  """The lines of the deck (#202), from what the controller recorded."""
  template = creation["template"]
  origin = f" (default for {type_})" if template.get("default") and type_ else ""
  lines = [
    f"golden path “{template['name']}”{origin}: repo {creation['repo']['fullName']} created",
    "registered in the catalog (lifecycle: experimental)",
  ]
  added = [path for path in ANNOUNCED if path in (creation.get("files") or [])]
  if added:
    lines.append(f"{' and '.join(added)} added to the repo")
  app_spec = creation.get("appSpec")
  if app_spec is not None:
    parts = (["container"] if app_spec.get("containers") else []) + list(app_spec.get("resources") or []) + [f"route {route}" for route in app_spec.get("routes") or []]
    lines.append(f"app-spec.yaml generated: {', '.join(parts)}" if parts else "app-spec.yaml generated")
  return lines


def _where(component: str, item: dict) -> str:
  """The environment of the default instance; <instance>@<environment> for an extra one (#294)."""
  instance = item.get("instance")
  return item["environment"] if instance in (None, component) else f"{instance}@{item['environment']}"


def _steps(creation: dict, indent: int = 2) -> None:
  for condition in creation.get("conditions") or []:
    typer.echo(f"{' ' * indent}{_mark(condition, '✗')} {condition['type'].ljust(12)} {condition.get('message') or condition.get('reason')}")


def _wait(client: PlatformClient, creation: dict, timeout: int, quiet: bool) -> dict:
  deadline = time.monotonic() + timeout
  shown = set()
  while True:
    for condition in creation.get("conditions") or []:
      key = (condition["type"], condition["status"], condition.get("reason"))
      if key not in shown and condition["type"] != "Ready" and not quiet:
        typer.echo(f"  {_mark(condition, '…')} {condition['type']}: {condition.get('message') or condition.get('reason')}", err=True)
        shown.add(key)
    ready = _ready(creation)
    if ready.get("status") == "True":
      return creation
    if ready.get("reason") in FINAL:
      typer.secho(f"✗ {creation['name']}: {ready['reason']}: {ready.get('message')}", fg=typer.colors.RED, err=True)
      if ready["reason"] in STOPPED:
        typer.echo(f"  rename it, request it again with --replace, or free the name with: platform catalog component creation delete {creation['name']}", err=True)
      raise typer.Exit(1)
    if time.monotonic() > deadline:
      fail(f"{creation['name']} not created after {timeout}s (status: {creation['status']})")
    time.sleep(2)
    creation = client.component_creation(creation["name"])


@app.command("create", epilog=examples(
  "platform catalog component create hello-api --system messaging --type service --wait",
  "platform catalog component create hello-api --system messaging --owner team-a --template python-service --param port=8080",
  "platform catalog component create hello-api --system messaging --replace --wait",
))
def create(
  name: Annotated[str, typer.Argument(help="Name of the new component, also the repo name.")],
  system: Annotated[str, typer.Option(help="System the component belongs to.")],
  owner: Annotated[str | None, typer.Option(help="Owner team; defaults to your team when you have only one.")] = None,
  type_: Annotated[str | None, typer.Option("--type", help="service, website or library: picks the default template of the type.")] = None,
  template: Annotated[str | None, typer.Option(help="A registered template instead of the default of the type.")] = None,
  param: Annotated[list[str], typer.Option("--param", help="Extra template parameter as key=value; repeatable.")] = [],
  description: Annotated[str | None, typer.Option(help="One line about it.")] = None,
  scm: Annotated[str | None, typer.Option(help="SCM connection; defaults to the default connection.")] = None,
  visibility: Annotated[str | None, typer.Option(help="public or private; defaults to the connection's.")] = None,
  prd: Annotated[str | None, typer.Option(help="File that seeds docs/prd.md ('-' reads stdin).")] = None,
  replace: Annotated[bool, typer.Option("--replace", help="Take the place of a stopped creation with this name (yours, or any as platform-admins).")] = False,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until the repo is created and registered.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait with --wait.")] = 300,
  output: OutputOption = Format.table,
):
  """Create the repo of a component from a template and register it in the catalog."""
  if type_ and template:
    fail("give --type or --template, not both")
  if visibility not in (None, "public", "private"):
    fail(f"--visibility takes public or private, got '{visibility}'")
  body = {
    "name": name, "system": system, "owner": owner, "type": type_, "template": template, "description": description,
    "params": _params(param), "scm": scm, "visibility": visibility, "prd": _prd(prd), "replace": replace or None,
  }
  client = _client()
  try:
    creation = client.create_component({key: value for key, value in body.items() if value is not None})
    if wait:
      creation = _wait(client, creation, timeout, quiet=output.data)
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(creation, output)
  elif wait:
    for line in summary(creation, None if template else (type_ or "service")):
      success(line)
    for line in warnings(creation):
      typer.secho(f"⚠ {line}", fg=typer.colors.YELLOW)
  else:
    typer.echo(f"creating {name} from template {creation['template']['name']}@{creation['template']['ref']} …")
    typer.echo(f"follow it with: platform catalog component get {name}")


@app.command("list", epilog=examples(
  "platform catalog component list",
  "platform catalog component list --system messaging --owner team-a",
))
def list_(
  system: Annotated[str | None, typer.Option(help="Only this system.")] = None,
  owner: Annotated[str | None, typer.Option(help="Only this owner team.")] = None,
  output: OutputOption = Format.table,
):
  """List the components in the index."""
  try:
    items = _client().list_components(system, owner)
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(items, output)
    return
  rows = [[item["name"], item.get("system") or "—", item.get("owner") or "—", item.get("lifecycle") or "—", item.get("template") or "—"] for item in items]
  print_table(["NAME", "SYSTEM", "OWNER", "LIFECYCLE", "TEMPLATE"], rows)


def _build_line(item: dict) -> str:
  parts = [item["status"], item.get("version"), age(item.get("createdAt"))]
  return f"{item['name']} ({', '.join(part for part in parts if part)})"


def _version_line(item: dict) -> str:
  parts = [(item.get("commit") or "")[:7], item.get("branch"), age(item.get("createdAt"))]
  return f"{item['version']} ({', '.join(part for part in parts if part)})"


def _section(label: str, lines: list[str], verbose: bool, hide_empty: bool) -> None:
  """One line with the newest item, and how many more --verbose shows; every item with --verbose."""
  if not lines:
    if not hide_empty:
      typer.echo(f"  {label.ljust(12)} —")
    return
  shown = lines if verbose else [lines[0] + (f"  +{len(lines) - 1} more (--verbose)" if len(lines) > 1 else "")]
  typer.echo(f"  {label.ljust(12)} {shown[0]}")
  for line in shown[1:]:
    typer.echo(f"  {''.ljust(12)} {line}")


def _next(component: dict) -> None:
  name = (component["name"], "component")
  steps = []
  if component.get("builds"):
    steps.append(("platform build get", (component["builds"][0]["name"], "key"), {}))
  steps.append(("platform build list", None, {"--component": name}))
  steps.append(("platform workload list", None, {"--component": name}))
  if component.get("creation"):
    steps.append(("platform catalog component creation get", name, {}))
  steps.append(("platform catalog component clone", name, {}))
  next_steps(steps)


@app.command("get", epilog=examples(
  "platform catalog component get hello-api",
  "platform catalog component get hello-api --verbose",
  "platform catalog component get hello-api --hide-empty --output json",
))
def get(
  name: Annotated[str, typer.Argument(help="Component name (platform catalog component list).")],
  verbose: Annotated[bool, typer.Option("--verbose", help="Every build and version it carries, and the creation steps.")] = False,
  hide_empty: Annotated[bool, typer.Option("--hide-empty", help="Leave out empty fields: the — lines, and null or empty keys in data output.")] = False,
  output: OutputOption = Format.table,
):
  """Show a component and what it generated: its creation, newest builds and versions, where it runs."""
  client = _client()
  try:
    component = client.get_component(name)
  except ApiError as error:
    try:
      creation = client.component_creation(name)
    except ApiError:
      fail(str(error))
    if output.data:
      print_data(drop_empty(creation) if hide_empty else creation, output)
      return
    typer.echo(f"component/{name} (creating: {creation['status']})")
    _steps(creation)
    return
  if output.data:
    print_data(drop_empty(component) if hide_empty else component, output)
    return
  typer.echo(f"component/{component['name']}")
  for field in ("system", "owner", "type", "lifecycle", "repo", "template", "description"):
    if component.get(field) or not hide_empty:
      typer.echo(f"  {field.ljust(12)} {component.get(field) or '—'}")
  # Only who requested the creation and platform-admins see it; for anyone else the line is left out.
  creation = component.get("creation")
  if creation:
    typer.echo(f"  {'creation'.ljust(12)} {creation['status']}, {age(creation.get('createdAt'))} ago")
    if verbose:
      _steps(creation, indent=15)
  _section("builds", [_build_line(item) for item in component.get("builds") or []], verbose, hide_empty)
  _section("versions", [_version_line(item) for item in component.get("versions") or []], verbose, hide_empty)
  # Only the environments you can use (ADR 0033).
  running = ", ".join(f"{_where(component['name'], item)} ({item.get('version') or '—'}, {item['status']})" for item in component.get("runningIn") or [])
  if running or not hide_empty:
    typer.echo(f"  {'running in'.ljust(12)} {running or '—'}")
  _next(component)


@app.command("clone", epilog=examples(
  "platform catalog component clone hello-api",
  "platform catalog component clone hello-api --https --directory ~/src/hello-api",
))
def clone(
  name: Annotated[str, typer.Argument(help="Component name (platform catalog component list).")],
  directory: Annotated[str | None, typer.Option(help="Where to clone; defaults to the repo name.")] = None,
  https: Annotated[bool, typer.Option("--https", help="Clone over HTTPS instead of SSH; wins over git_protocol in the config.")] = False,
):
  """Clone the repo of a component with your own Git credentials."""
  protocol = "https" if https else config.load().get("git_protocol", "ssh")
  if protocol not in GIT_URLS:
    fail(f"git_protocol takes ssh or https, got '{protocol}' (in {config.config_path()})")
  client = _client()
  try:
    component = client.get_component(name)
  except ApiError as error:
    try:
      client.component_creation(name)
    except ApiError:
      fail(f"{error}: see the components with platform catalog component list")
    fail(f"{name} is still being created: follow it with platform catalog component get {name}")
  repo = component.get("repo") or ""
  if not REPO.fullmatch(repo):
    fail(f"{name}: repo '{repo}' is not <org>/<repo>")
  url = GIT_URLS[protocol].format(repo=repo)
  target = [directory] if directory else []
  typer.echo(f"# git clone {' '.join([url, *target])}")
  # The platform hands out no credential: git uses the developer's own, and its output passes through.
  raise typer.Exit(subprocess.run(["git", "clone", "--", url, *target]).returncode)


@creation_app.command("list", epilog=examples("platform catalog component creation list"))
def creation_list(output: OutputOption = Format.table):
  """List the creations you requested (all of them for platform-admins), with when each frees its name."""
  try:
    items = _client().list_component_creations()
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(items, output)
    return
  rows = [[item["name"], item["status"], item.get("step") or "—", item.get("requestedBy") or "—", age(item.get("createdAt")), remaining(item.get("freesAt"), utcnow())] for item in items]
  print_table(["NAME", "STATUS", "STEP", "REQUESTED BY", "AGE", "FREES IN"], rows)


@creation_app.command("get", epilog=examples("platform catalog component creation get hello-api"))
def creation_get(name: Annotated[str, typer.Argument(help="Component name (platform catalog component creation list).")], output: OutputOption = Format.table):
  """Show the steps of a creation."""
  try:
    creation = _client().component_creation(name)
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(creation, output)
    return
  typer.echo(f"componentcreation/{name} ({creation['status']})")
  _steps(creation)


@creation_app.command("delete", epilog=examples("platform catalog component creation delete hello-api"))
def creation_delete(name: Annotated[str, typer.Argument(help="Component name (platform catalog component creation list).")]):
  """Delete a stopped or finished creation and free its name; a running one is refused."""
  try:
    _client().delete_component_creation(name)
  except ApiError as error:
    fail(str(error))
  success(f"creation of {name} deleted: {name} is free")
