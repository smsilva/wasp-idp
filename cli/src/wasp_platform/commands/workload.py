"""platform workload: the Workload Spec of a version (#291, ADR 0033).

The Workload Spec is the app-spec.yaml (Score) of a version, immutable, kept in the version index by
the build. spec validate runs the same gate as the build on a local file, before any build.
"""
from pathlib import Path
from typing import Annotated

import typer
import yaml

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, success

# The kube API keeps the spec as JSON with sorted keys: the top level goes back to the order of a Score.
SCORE_ORDER = ("apiVersion", "metadata", "resources", "containers", "service")

app = typer.Typer(help="Workloads: a version of a component and its Workload Spec (Score).", no_args_is_help=True)
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
