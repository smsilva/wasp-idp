"""platform workload: the Workload Spec of a version and its Workload Instances (#291, #292, ADR 0033).

The Workload Spec is the app-spec.yaml (Score) of a version, immutable, kept in the version index by
the build. spec validate runs the same gate as the build on a local file, before any build. A Workload
Instance is a Workload Spec live in an environment, as a Helm release is a chart installed: each deploy
is a new revision, and its short name is <instance>@<environment> (in phase 1 the instance is the
component).
"""
import time
from pathlib import Path
from typing import Annotated

import typer
import yaml

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, print_table, success

# The kube API keeps the spec as JSON with sorted keys: the top level goes back to the order of a Score.
SCORE_ORDER = ("apiVersion", "metadata", "resources", "containers", "service")

app = typer.Typer(help="Workloads: the Workload Spec (Score) of a version, and its instances in environments.", no_args_is_help=True)
spec_app = typer.Typer(help="The Workload Spec: the app-spec.yaml (Score) of a version.", no_args_is_help=True)
app.add_typer(spec_app, name="spec")


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def _resources(items: list[dict]) -> str:
  """db (postgres), dns, route: the name, and the type when it differs."""
  return ", ".join(item["name"] if item["name"] == item["type"] else f"{item['name']} ({item['type']})" for item in items)


@spec_app.command("validate")
def validate(
  file: Annotated[Path, typer.Option(help="The Score file to validate.")] = Path("app-spec.yaml"),
  output: OutputOption = Format.table,
):
  """Validate an app-spec.yaml with the gate of the build: schema, resource types, resources in the catalog."""
  try:
    content = file.read_text(encoding="utf-8")
  except OSError as error:
    fail(f"cannot read {file}: {error.strerror}")
  try:
    result = _client().validate_workload_spec(content)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(result)
  elif result["valid"]:
    resources = _resources(result["resources"])
    success(f"{file.name} valid · {resources}" if resources else f"{file.name} valid")
  else:
    for error in result["errors"]:
      typer.secho(f"  {error['field']}: {error['reason']}", fg=typer.colors.RED, err=True)
  if not result["valid"]:
    if output == Format.json:
      raise typer.Exit(1)
    fail(f"{file.name}: {len(result['errors'])} error(s)")


@spec_app.command("get")
def get(
  component: Annotated[str, typer.Option(help="Component whose spec to show.")],
  version: Annotated[str | None, typer.Option(help="Version from the index; by default the newest.")] = None,
  branch: Annotated[str | None, typer.Option(help="The newest version built from this branch.")] = None,
  output: OutputOption = Format.table,
):
  """Show the Workload Spec of a version, as YAML ready for a file."""
  if version is not None and branch is not None:
    fail("--version and --branch are exclusive")
  try:
    spec = _client().get_workload_spec(component, version, branch)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(spec)
    return
  # A YAML comment: the output stays a valid app-spec.yaml.
  typer.echo(f"# {spec['component']} {spec['version']} · {spec['branch']} @ {(spec.get('commit') or '')[:7]}")
  document = spec["appSpec"]
  ordered = {key: document[key] for key in SCORE_ORDER if key in document} | document
  typer.echo(yaml.safe_dump(ordered, sort_keys=False).rstrip())


def _replicas(item: dict) -> str:
  replicas = item.get("replicas") or {}
  return f"{replicas.get('ready')}/{replicas.get('desired')}" if replicas else "—"


def _wait(client: PlatformClient, revision: dict, timeout: int) -> dict:
  """Until the provider closes the revision: Succeeded, or a reason that waiting does not heal."""
  deadline = time.monotonic() + timeout
  while revision["open"]:
    if time.monotonic() > deadline:
      fail(f"{revision['instance']}@{revision['environment']} revision {revision['revision']} not done after {timeout}s ({revision['status']}: {revision.get('message') or '—'})")
    time.sleep(3)
    history = client.workload_history(revision["environment"], revision["instance"])
    revision = next(item for item in history if item["revision"] == revision["revision"])
  return revision


@app.command("deploy")
def deploy(
  component: Annotated[str, typer.Option(help="Component to deploy; in phase 1 it names the instance.")],
  environment: Annotated[str, typer.Option(help="Environment to deploy to.")],
  version: Annotated[str | None, typer.Option(help="Version from the index.")] = None,
  branch: Annotated[str | None, typer.Option(help="The newest version built from this branch, pinned in the revision.")] = None,
  replicas: Annotated[int | None, typer.Option(min=0, max=20, help="Replicas in this environment; by default 1.")] = None,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until the rollout ends.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait with --wait.")] = 300,
  output: OutputOption = Format.table,
):
  """Deploy a version to an environment: a new revision of the instance."""
  if (version is None) == (branch is None):
    fail("give either --version or --branch")
  body = {key: value for key, value in (("version", version), ("branch", branch), ("replicas", replicas)) if value is not None}
  client = _client()
  try:
    revision = client.deploy_workload(environment, component, body)
    if wait:
      revision = _wait(client, revision, timeout)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(revision)
    if wait and revision["status"] != "Succeeded":
      raise typer.Exit(1)
    return
  name = f"{revision['instance']}@{revision['environment']} revision {revision['revision']}"
  if not wait:
    typer.echo(f"{name}: deploying {revision['version']} …")
    typer.echo(f"follow it with: platform workload get --component {component} --environment {environment}")
  elif revision["status"] == "Succeeded":
    success(f"{name}: {revision['version']} running · {revision.get('message') or '—'}")
  else:
    fail(f"{name}: {revision['status']}: {revision.get('message') or '—'}")


@app.command("list")
def list_(
  environment: Annotated[str, typer.Option(help="Environment whose workloads to list.")],
  output: OutputOption = Format.table,
):
  """List the workloads of an environment: version, status, replicas, revision, URL."""
  try:
    items = _client().list_workloads(environment)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(items)
    return
  print_table(
    ["WORKLOAD", "VERSION", "STATUS", "REPLICAS", "REVISION", "URL"],
    [[item["name"], item.get("version") or "—", item["status"], _replicas(item), str(item.get("revision") or "—"), item.get("url") or "—"] for item in items],
  )


@app.command("get")
def get_(
  component: Annotated[str, typer.Option(help="Component of the workload.")],
  environment: Annotated[str, typer.Option(help="Environment of the workload.")],
  output: OutputOption = Format.table,
):
  """Show a workload in an environment and its newest revision."""
  try:
    item = _client().get_workload(environment, component)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(item)
    return
  latest = item["latestRevision"]
  typer.echo(f"{item['name']} ({item['status']})")
  for field, value in (
    ("component", item.get("component")),
    ("version", item.get("version")),
    ("image", item.get("image")),
    ("replicas", _replicas(item)),
    ("revision", item.get("revision")),
    ("url", item.get("url")),
    ("message", item.get("message")),
  ):
    typer.echo(f"  {field.ljust(13)} {value or '—'}")
  if latest["revision"] != item.get("revision"):
    typer.echo(f"  {'newest'.ljust(13)} revision {latest['revision']} ({latest['action']} {latest.get('version') or ''}): {latest['status']}: {latest.get('message') or '—'}")


@app.command("history")
def history(
  environment: Annotated[str, typer.Option(help="Environment whose revisions to list.")],
  component: Annotated[str | None, typer.Option(help="Only the revisions of this component.")] = None,
  output: OutputOption = Format.table,
):
  """List the revisions of an environment, oldest first: who asked for what, and how it ended."""
  try:
    items = _client().workload_history(environment, component)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(items)
    return
  print_table(
    ["WORKLOAD", "REVISION", "ACTION", "VERSION", "STATUS", "BY", "CREATED"],
    [[f"{item['instance']}@{item['environment']}", str(item["revision"]), item["action"], item.get("version") or "—", item["status"], item.get("requestedBy") or "—", item.get("createdAt") or "—"] for item in items],
  )
