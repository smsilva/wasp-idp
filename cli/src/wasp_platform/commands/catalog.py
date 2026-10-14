"""The catalog: domains, systems, resources and templates the platform stores (ADRs 0023 and 0024).

Components live in each repo's catalog-info.yaml: `component` creates the repo and reads the index.
"""
from enum import Enum
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, examples, fail, print_data, print_table, success
from .catalog_import import import_catalog
from .component import app as component_app
from .template import app as template_app

app = typer.Typer(help="The catalog: domains, systems, resources, components and templates.", no_args_is_help=True)

# Table columns of each kind after NAME: (header, field of the API view).
COLUMNS = {
  "domains": [("PARENT", "parent"), ("OWNER", "owner")],
  "systems": [("DOMAIN", "domain"), ("OWNER", "owner")],
  "resources": [("TYPE", "type"), ("SYSTEM", "system"), ("OWNER", "owner")],
}

SAMPLES = {"domain": "communication", "system": "messaging", "resource": "messaging-db"}

Owner = Annotated[str, typer.Option(help="Owner team, such as team-alpha.")]
Description = Annotated[str | None, typer.Option(help="One line about it.")]


class Kind(str, Enum):
  domain = "domain"
  system = "system"
  resource = "resource"


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def _cell(value) -> str:
  return value or "—"


def _create(plural: str, singular: str, body: dict, output: Format) -> None:
  try:
    entity = _client().create_catalog_entity(plural, {key: value for key, value in body.items() if value is not None})
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(entity, output)
  else:
    success(f"{singular} {entity['name']} created")


def _kind_app(plural: str, singular: str, help_text: str) -> typer.Typer:
  """list, get and delete are the same for every kind; create differs and is added per kind."""
  sub = typer.Typer(help=help_text, no_args_is_help=True)
  name_help = f"{singular.capitalize()} name (platform catalog {singular} list)."

  @sub.command("list", help=f"List {plural}.", epilog=examples(f"platform catalog {singular} list", f"platform catalog {singular} list --output json"))
  def list_(output: OutputOption = Format.table):
    try:
      items = _client().list_catalog(plural)
    except ApiError as error:
      fail(str(error))
    if output.data:
      print_data(items, output)
      return
    headers = ["NAME", *[header for header, _ in COLUMNS[plural]]]
    rows = [[item["name"], *[_cell(item.get(field)) for _, field in COLUMNS[plural]]] for item in items]
    print_table(headers, rows)

  @sub.command("get", help=f"Show a {singular} and what depends on it.", epilog=examples(f"platform catalog {singular} get {SAMPLES[singular]}", f"platform catalog {singular} get {SAMPLES[singular]} --output json"))
  def get(name: Annotated[str, typer.Argument(help=name_help)], output: OutputOption = Format.table):
    try:
      entity = _client().get_catalog_entity(plural, name)
    except ApiError as error:
      fail(str(error))
    if output.data:
      print_data(entity, output)
      return
    typer.echo(f"{singular}/{entity['name']}")
    fields = [field for _, field in COLUMNS[plural]] + ["description"]
    for field in fields:
      typer.echo(f"  {field.ljust(12)} {_cell(entity.get(field))}")
    typer.echo(f"  {'dependents'.ljust(12)} {', '.join(entity.get('dependents') or []) or 'none'}")

  @sub.command("delete", help=f"Delete a {singular}; refused while something depends on it.", epilog=examples(f"platform catalog {singular} delete {SAMPLES[singular]}"))
  def delete(name: Annotated[str, typer.Argument(help=name_help)], output: OutputOption = Format.table):
    try:
      _client().delete_catalog_entity(plural, name)
    except ApiError as error:
      fail(str(error))
    if output.data:
      print_data({"kind": singular, "name": name, "status": "deleted"}, output)
    else:
      success(f"{singular} {name} deleted")

  return sub


domain_app = _kind_app("domains", "domain", "Business areas; --parent makes a subdomain.")
system_app = _kind_app("systems", "system", "Capabilities inside a domain.")
resource_app = _kind_app("resources", "resource", "Infrastructure a system needs, described by its role.")


@domain_app.command("create", epilog=examples(
  "platform catalog domain create communication --owner team-a",
  "platform catalog domain create chat --owner team-a --parent communication",
))
def create_domain(
  name: Annotated[str, typer.Argument(help="Name of the new domain.")],
  owner: Owner,
  parent: Annotated[str | None, typer.Option(help="Parent domain: makes this a subdomain.")] = None,
  description: Description = None,
  output: OutputOption = Format.table,
):
  """Create a domain (platform-admins only)."""
  _create("domains", "domain", {"name": name, "owner": owner, "parent": parent, "description": description}, output)


@system_app.command("create", epilog=examples(
  "platform catalog system create messaging --domain communication --owner team-a",
))
def create_system(
  name: Annotated[str, typer.Argument(help="Name of the new system.")],
  domain: Annotated[str, typer.Option(help="Domain the system belongs to.")],
  owner: Owner,
  description: Description = None,
  output: OutputOption = Format.table,
):
  """Create a system."""
  _create("systems", "system", {"name": name, "owner": owner, "domain": domain, "description": description}, output)


@resource_app.command("create", epilog=examples(
  "platform catalog resource create messaging-db --type database --system messaging --owner team-a",
))
def create_resource(
  name: Annotated[str, typer.Argument(help="Name of the new resource.")],
  type_: Annotated[str, typer.Option("--type", help="Role, not a cloud service: database, topic, queue, bucket.")],
  system: Annotated[str, typer.Option(help="System the resource belongs to.")],
  owner: Owner,
  description: Description = None,
  output: OutputOption = Format.table,
):
  """Create a resource shared by the components of a system."""
  _create("resources", "resource", {"name": name, "owner": owner, "type": type_, "system": system, "description": description}, output)


@app.command("list", epilog=examples(
  "platform catalog list",
  "platform catalog list --kind system --owner team-a",
))
def list_all(
  kind: Annotated[Kind | None, typer.Option(help="Only this kind.")] = None,
  owner: Annotated[str | None, typer.Option(help="Only this owner team.")] = None,
  output: OutputOption = Format.table,
):
  """List every entity of the catalog, parents first."""
  try:
    items = _client().list_catalog_entities(kind.value if kind else None, owner)
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(items, output)
    return
  print_table(["KIND", "NAME", "PARENT", "OWNER"], [[item["kind"], item["name"], _cell(item.get("parent")), item["owner"]] for item in items])


app.add_typer(domain_app, name="domain")
app.add_typer(system_app, name="system")
app.add_typer(resource_app, name="resource")
app.add_typer(component_app, name="component")
app.add_typer(template_app, name="template")
app.command("import", epilog=examples(
  "platform catalog import catalog/ --dry-run",
  "platform catalog import catalog/ --yes",
))(import_catalog)
