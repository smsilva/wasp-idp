"""The catalog: domains, systems and resources the platform stores (ADR 0023).

Components and APIs live in each repo's catalog-info.yaml and arrive in a later slice.
"""
from enum import Enum
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, print_table, success

app = typer.Typer(help="The catalog: domains, systems and resources.", no_args_is_help=True)

# Table columns of each kind after NAME: (header, field of the API view).
COLUMNS = {
  "domains": [("PARENT", "parent"), ("OWNER", "owner")],
  "systems": [("DOMAIN", "domain"), ("OWNER", "owner")],
  "resources": [("TYPE", "type"), ("SYSTEM", "system"), ("OWNER", "owner")],
}

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
  if output == Format.json:
    print_json(entity)
  else:
    success(f"{singular} {entity['name']} created")


def _kind_app(plural: str, singular: str, help_text: str) -> typer.Typer:
  """list, get and delete are the same for every kind; create differs and is added per kind."""
  sub = typer.Typer(help=help_text, no_args_is_help=True)

  @sub.command("list", help=f"List {plural}.")
  def list_(output: OutputOption = Format.table):
    try:
      items = _client().list_catalog(plural)
    except ApiError as error:
      fail(str(error))
    if output == Format.json:
      print_json(items)
      return
    headers = ["NAME", *[header for header, _ in COLUMNS[plural]]]
    rows = [[item["name"], *[_cell(item.get(field)) for _, field in COLUMNS[plural]]] for item in items]
    print_table(headers, rows)

  @sub.command("get", help=f"Show a {singular} and what depends on it.")
  def get(name: str, output: OutputOption = Format.table):
    try:
      entity = _client().get_catalog_entity(plural, name)
    except ApiError as error:
      fail(str(error))
    if output == Format.json:
      print_json(entity)
      return
    typer.echo(f"{singular}/{entity['name']}")
    fields = [field for _, field in COLUMNS[plural]] + ["description"]
    for field in fields:
      typer.echo(f"  {field.ljust(12)} {_cell(entity.get(field))}")
    typer.echo(f"  {'dependents'.ljust(12)} {', '.join(entity.get('dependents') or []) or 'none'}")

  @sub.command("delete", help=f"Delete a {singular}; refused while something depends on it.")
  def delete(name: str, output: OutputOption = Format.table):
    try:
      _client().delete_catalog_entity(plural, name)
    except ApiError as error:
      fail(str(error))
    if output == Format.json:
      print_json({"kind": singular, "name": name, "status": "deleted"})
    else:
      success(f"{singular} {name} deleted")

  return sub


domain_app = _kind_app("domains", "domain", "Business areas; --parent makes a subdomain.")
system_app = _kind_app("systems", "system", "Capabilities inside a domain.")
resource_app = _kind_app("resources", "resource", "Infrastructure a system needs, described by its role.")


@domain_app.command("create")
def create_domain(
  name: str,
  owner: Owner,
  parent: Annotated[str | None, typer.Option(help="Parent domain: makes this a subdomain.")] = None,
  description: Description = None,
  output: OutputOption = Format.table,
):
  """Create a domain (platform-admins only)."""
  _create("domains", "domain", {"name": name, "owner": owner, "parent": parent, "description": description}, output)


@system_app.command("create")
def create_system(
  name: str,
  domain: Annotated[str, typer.Option(help="Domain the system belongs to.")],
  owner: Owner,
  description: Description = None,
  output: OutputOption = Format.table,
):
  """Create a system."""
  _create("systems", "system", {"name": name, "owner": owner, "domain": domain, "description": description}, output)


@resource_app.command("create")
def create_resource(
  name: str,
  type_: Annotated[str, typer.Option("--type", help="Role, not a cloud service: database, topic, queue, bucket.")],
  system: Annotated[str, typer.Option(help="System the resource belongs to.")],
  owner: Owner,
  description: Description = None,
  output: OutputOption = Format.table,
):
  """Create a resource shared by the components of a system."""
  _create("resources", "resource", {"name": name, "owner": owner, "type": type_, "system": system, "description": description}, output)


@app.command("list")
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
  if output == Format.json:
    print_json(items)
    return
  print_table(["KIND", "NAME", "PARENT", "OWNER"], [[item["kind"], item["name"], _cell(item.get("parent")), item["owner"]] for item in items])


app.add_typer(domain_app, name="domain")
app.add_typer(system_app, name="system")
app.add_typer(resource_app, name="resource")
