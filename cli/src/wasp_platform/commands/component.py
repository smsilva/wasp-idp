"""platform catalog component: create a repo through the golden path, and read the component index (#204).

A component lives in its repo's catalog-info.yaml (ADR 0023): the platform creates the repo and
indexes it; changing a component is a pull request in its repo.
"""
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from .. import config
from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, print_table, success
from .template import _params

app = typer.Typer(help="Components: repos created through the golden path, and the index.", no_args_is_help=True)

# Ready=False with these reasons does not heal by waiting: --wait stops at once.
FINAL = {"RepoAlreadyExists", "RepoGone", "ComponentExists", "GitHubRejected", "ConnectionNotFound", "ConnectionNotReady", "CredentialMissing"}
# Protected=False with this reason is a warning: main is unprotected (a private repo on GitHub Free), the
# creation still ends Ready.
UNPROTECTED = "ProtectionUnavailable"
# The only SCM vendor is GitHub (#199): repo is <org>/<repo> on github.com.
GIT_URLS = {"ssh": "git@github.com:{repo}.git", "https": "https://github.com/{repo}.git"}
REPO = re.compile(r"[\w.-]+/[\w.-]+")
# Files the summary names when the template generated them.
ANNOUNCED = ("docs/prd.md", "AGENTS.md")


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
      fail(f"{creation['name']}: {ready['reason']}: {ready.get('message')}")
    if time.monotonic() > deadline:
      fail(f"{creation['name']} not created after {timeout}s (status: {creation['status']})")
    time.sleep(2)
    creation = client.component_creation(creation["name"])


@app.command("create")
def create(
  name: str,
  system: Annotated[str, typer.Option(help="System the component belongs to.")],
  owner: Annotated[str | None, typer.Option(help="Owner team; defaults to your team when you have only one.")] = None,
  type_: Annotated[str | None, typer.Option("--type", help="service, website or library: picks the default template of the type.")] = None,
  template: Annotated[str | None, typer.Option(help="A registered template instead of the default of the type.")] = None,
  param: Annotated[list[str], typer.Option("--param", help="Extra template parameter as key=value; repeatable.")] = [],
  description: Annotated[str | None, typer.Option(help="One line about it.")] = None,
  scm: Annotated[str | None, typer.Option(help="SCM connection; defaults to the default connection.")] = None,
  visibility: Annotated[str | None, typer.Option(help="public or private; defaults to the connection's.")] = None,
  prd: Annotated[str | None, typer.Option(help="File that seeds docs/prd.md ('-' reads stdin).")] = None,
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
    "params": _params(param), "scm": scm, "visibility": visibility, "prd": _prd(prd),
  }
  client = _client()
  try:
    creation = client.create_component({key: value for key, value in body.items() if value is not None})
    if wait:
      creation = _wait(client, creation, timeout, quiet=output == Format.json)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(creation)
  elif wait:
    for line in summary(creation, None if template else (type_ or "service")):
      success(line)
    for line in warnings(creation):
      typer.secho(f"⚠ {line}", fg=typer.colors.YELLOW)
  else:
    typer.echo(f"creating {name} from template {creation['template']['name']}@{creation['template']['ref']} …")
    typer.echo(f"follow it with: platform catalog component get {name}")


@app.command("list")
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
  if output == Format.json:
    print_json(items)
    return
  rows = [[item["name"], item.get("system") or "—", item.get("owner") or "—", item.get("lifecycle") or "—", item.get("template") or "—"] for item in items]
  print_table(["NAME", "SYSTEM", "OWNER", "LIFECYCLE", "TEMPLATE"], rows)


@app.command("get")
def get(name: str, output: OutputOption = Format.table):
  """Show a component; while its creation runs, show the creation steps instead."""
  client = _client()
  try:
    component = client.get_component(name)
  except ApiError as error:
    try:
      creation = client.component_creation(name)
    except ApiError:
      fail(str(error))
    if output == Format.json:
      print_json(creation)
      return
    typer.echo(f"component/{name} (creating: {creation['status']})")
    for condition in creation.get("conditions") or []:
      typer.echo(f"  {_mark(condition, '✗')} {condition['type'].ljust(12)} {condition.get('message') or condition.get('reason')}")
    return
  if output == Format.json:
    print_json(component)
    return
  typer.echo(f"component/{component['name']}")
  for field in ("system", "owner", "type", "lifecycle", "repo", "template", "description"):
    typer.echo(f"  {field.ljust(12)} {component.get(field) or '—'}")
  # Only the environments you can use (ADR 0033).
  running = ", ".join(f"{_where(component['name'], item)} ({item.get('version') or '—'}, {item['status']})" for item in component.get("runningIn") or [])
  typer.echo(f"  {'running in'.ljust(12)} {running or '—'}")


@app.command("clone")
def clone(
  name: str,
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
