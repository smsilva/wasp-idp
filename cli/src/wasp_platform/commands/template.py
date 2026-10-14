"""platform catalog template: the golden paths a component is created from (ADR 0024).

The registry lives in the Platform API; the content stays in Git. `render` runs locally, so whoever
writes a template sees the result without creating a repo.
"""
import tempfile
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from wasp_templates.render import RenderError, annotate_origin, load_template, render as render_files
from wasp_templates.source import SourceError, coerce, fetch

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, examples, fail, print_data, print_table, success
from .catalog_import import ImportFileError, Ref, Repo, origin, read_documents, run_import

app = typer.Typer(help="Templates a component is created from; one default per type.", no_args_is_help=True)


class Type(str, Enum):
  service = "service"
  website = "website"
  library = "library"


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def _location(source: dict | None) -> str:
  if not source:
    return "—"
  return f"{source['repo'].rstrip('/')}/{source['path']}"


@app.command("list", epilog=examples(
  "platform catalog template list",
  "platform catalog template list --output json",
))
def list_(output: OutputOption = Format.table):
  """List templates."""
  try:
    items = _client().list_templates()
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(items, output)
    return
  rows = [
    [item["name"], item["type"], (item.get("source") or {}).get("ref", "—"), "yes" if item.get("default") else "—", _location(item.get("source"))]
    for item in items
  ]
  print_table(["NAME", "TYPE", "REF", "DEFAULT", "SOURCE"], rows)


def _parameter_lines(parameters: dict) -> list[str]:
  required = set(parameters.get("required") or [])
  lines = []
  for name, schema in (parameters.get("properties") or {}).items():
    details = [schema.get("type", "string")]
    if "default" in schema:
      details.append(f"default {schema['default']}")
    elif name in required:
      details.append("required")
    if "enum" in schema:
      details.append("one of " + ", ".join(map(str, schema["enum"])))
    description = f": {schema['description']}" if schema.get("description") else ""
    lines.append(f"{name} ({', '.join(details)}){description}")
  return lines


@app.command("get", epilog=examples(
  "platform catalog template get python-service",
  "platform catalog template get python-service --output json",
))
def get(name: Annotated[str, typer.Argument(help="Template name (platform catalog template list).")], output: OutputOption = Format.table):
  """Show a template and the extra parameters it takes."""
  try:
    template = _client().get_template(name)
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(template, output)
    return
  source = template.get("source") or {}
  typer.echo(f"template/{template['name']}")
  for label, value in [
    ("type", template["type"]), ("default", "yes" if template.get("default") else "no"),
    ("repo", source.get("repo")), ("path", source.get("path")), ("ref", source.get("ref")),
    ("owner", template.get("owner")), ("description", template.get("description")),
  ]:
    typer.echo(f"  {label.ljust(12)} {value or '—'}")
  lines = _parameter_lines(template.get("parameters") or {})
  typer.echo(f"  {'parameters'.ljust(12)} {'none' if not lines else ''}".rstrip())
  for line in lines:
    typer.echo(f"    {line}")


@app.command("create", epilog=examples(
  "platform catalog template create python-service --type service --owner team-a --repo https://github.com/smsilva/wasp-idp --path platform/templates/python-service --ref main",
  "platform catalog template create python-service --type service --owner team-a --repo https://github.com/smsilva/wasp-idp --path platform/templates/python-service --ref main --default",
))
def create(
  name: Annotated[str, typer.Argument(help="Name of the new template.")],
  type_: Annotated[Type, typer.Option("--type", help="Kind of component it creates.")],
  owner: Annotated[str, typer.Option(help="Owner team of the template.")],
  repo: Annotated[str, typer.Option(help="https URL of the Git repo holding the template.")],
  path: Annotated[str, typer.Option(help="Folder of the content inside the repo.")],
  ref: Annotated[str, typer.Option(help="Tag or commit; a branch only while developing the template.")],
  default: Annotated[bool, typer.Option("--default", help="Make it the default of its type.")] = False,
  description: Annotated[str | None, typer.Option(help="One line about it.")] = None,
  output: OutputOption = Format.table,
):
  """Register a template whose content is already in Git (platform-admins only)."""
  body = {"name": name, "type": type_.value, "owner": owner, "default": default, "source": {"repo": repo, "path": path, "ref": ref}}
  if description:
    body["description"] = description
  try:
    template = _client().create_template(body)
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(template, output)
  else:
    success(f"template {template['name']} created" + (f", default for {template['type']}" if template.get("default") else ""))


@app.command("default", epilog=examples("platform catalog template default python-service"))
def make_default(name: Annotated[str, typer.Argument(help="Template name (platform catalog template list).")], output: OutputOption = Format.table):
  """Make a template the default of its type; the previous default stops being it (platform-admins only)."""
  try:
    template = _client().make_default_template(name)
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(template, output)
  else:
    success(f"template {name} is the default for {template['type']}")


@app.command("delete", epilog=examples("platform catalog template delete python-service"))
def delete(name: Annotated[str, typer.Argument(help="Template name (platform catalog template list).")], output: OutputOption = Format.table):
  """Delete a template; the default of a type goes only after another one takes its place (platform-admins only)."""
  try:
    _client().delete_template(name)
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data({"kind": "template", "name": name, "status": "deleted"}, output)
  else:
    success(f"template {name} deleted")


@app.command("import", epilog=examples(
  "platform catalog template import platform/templates/python-service --dry-run",
  "platform catalog template import templates/ --repo https://github.com/smsilva/wasp-idp --ref main --yes",
))
def import_templates(
  paths: Annotated[list[Path], typer.Argument(help="A template file or a folder (recursive): Backstage kind: Template or template.yaml in the platform format.")],
  repo: Repo = None,
  ref: Ref = None,
  dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the plan and exit.")] = False,
  yes: Annotated[bool, typer.Option("--yes", help="Apply without asking.")] = False,
  output: OutputOption = Format.table,
):
  """Import templates after reviewing the plan; the steps the platform does not run are listed as skipped."""
  source = origin(repo, ref)
  try:
    documents = read_documents(paths, templates_only=True)
  except ImportFileError as error:
    fail(str(error))
  run_import(documents, source, dry_run, yes, output, templates_only=True)


def _params(pairs: list[str]) -> dict:
  given = {}
  for pair in pairs:
    key, separator, value = pair.partition("=")
    if not separator or not key:
      fail(f"--param takes key=value, got '{pair}'")
    given[key] = value
  return given


@app.command("render", epilog=examples(
  "platform catalog template render python-service --name hello-api --output /tmp/hello-api",
  "platform catalog template render --from platform/templates/python-service --name hello-api --output /tmp/hello-api --param port=8080",
))
def render(
  name: Annotated[str | None, typer.Argument(help="Registered template; its content is fetched at the registered ref.")] = None,
  component: Annotated[str, typer.Option("--name", help="Name of the component, as component create would use it.")] = ...,
  output_dir: Annotated[Path, typer.Option("--output", help="Folder to create; must not exist.")] = ...,
  from_: Annotated[Path | None, typer.Option("--from", help="A local template folder (template.yaml + content/) instead of the registry.")] = None,
  param: Annotated[list[str], typer.Option("--param", help="Extra parameter as key=value; repeatable.")] = [],
  owner: Annotated[str, typer.Option(help="Owner team written into the result.")] = "team-example",
  system: Annotated[str | None, typer.Option(help="System written into the result.")] = None,
  description: Annotated[str, typer.Option(help="Description written into the result.")] = "Rendered by platform catalog template render",
):
  """Render a template locally, the way component create will: for whoever writes templates."""
  if (name is None) == (from_ is None):
    fail("give a template name or --from, not both")
  given = _params(param)
  base = {"name": component, "owner": owner, "system": system, "description": description}
  try:
    if from_ is not None:
      local = load_template(from_)
      values = {**coerce(local.parameters, given, local.name), **base}
      render_files(local.content, output_dir, values, local.copy_without_rendering)
      annotate_origin(output_dir, f"{local.name}@local")
    else:
      try:
        template = _client().get_template(name)
      except ApiError as error:
        fail(str(error))
      values = {**coerce(template.get("parameters") or {}, given, name), **base}
      with tempfile.TemporaryDirectory() as work:
        content = fetch(template["source"], Path(work))
        render_files(content, output_dir, values, template.get("copyWithoutRendering") or [])
      annotate_origin(output_dir, f"{name}@{template['source']['ref']}")
  except (RenderError, SourceError) as error:
    fail(str(error))
  success(f"rendered into {output_dir}")
