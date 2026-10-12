"""platform registry: the OCI registries a build pushes to (ADR 0037, #365).

platform-admins add them, anyone signed in lists them and picks one in `build create --registry`. At
most one is the default, the registry of a build without --registry. `--scm-connection` fills a ghcr
registry from a github connection: GHCR of the connection's org, pushed by the CI of its repos.
"""
from enum import Enum
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, print_table, success

app = typer.Typer(help="OCI registries: where builds push images (and, later, Helm charts and other OCI artifacts).", no_args_is_help=True)


class Vendor(str, Enum):
  ghcr = "ghcr"


def _call(function, *args):
  try:
    return function(PlatformClient(), *args)
  except ApiError as error:
    fail(str(error))


def _print(registry: dict) -> None:
  typer.echo(f"{registry['name']}: {registry['status']}" + (f" — {registry['message']}" if registry.get("message") else ""))
  for field, value in (
    ("vendor", registry.get("vendor")),
    ("address", registry.get("address")),
    ("default", "yes" if registry.get("default") else "no"),
    ("pull", registry.get("pullMode")),
  ):
    typer.echo(f"  {field.ljust(9)} {value or '—'}")


@app.command("add")
def add(
  name: str,
  scm_connection: Annotated[str | None, typer.Option("--scm-connection", help="A github SCM connection: the GHCR of its org (vendor ghcr, ghcr.io/<org>).")] = None,
  vendor: Annotated[Vendor | None, typer.Option(help="Registry vendor, without --scm-connection.")] = None,
  namespace: Annotated[str | None, typer.Option(help="The org (GHCR) images go under, without --scm-connection.")] = None,
  host: Annotated[str | None, typer.Option(help="Registry host; fixed for ghcr (ghcr.io).")] = None,
  default: Annotated[bool, typer.Option("--default", help="The registry of a build without --registry; the previous default stops being it.")] = False,
  output: OutputOption = Format.table,
):
  """Register an OCI registry (platform-admins only)."""
  body = {"name": name, "scmConnection": scm_connection, "vendor": vendor.value if vendor else None, "namespace": namespace, "host": host, "default": default}
  registry = _call(lambda client: client.add_registry({key: value for key, value in body.items() if value is not None}))
  if output == Format.json:
    print_json(registry)
    return
  success(f"registry {name} added{' (default)' if registry['default'] else ''} · {registry['address']}, pushed by the CI of {registry['namespace']} repos")


@app.command("list")
def list_(output: OutputOption = Format.table):
  """List the registries: NAME, VENDOR, ADDRESS, DEFAULT, STATUS."""
  items = _call(lambda client: client.list_registries())
  if output == Format.json:
    print_json(items)
    return
  print_table(["NAME", "VENDOR", "ADDRESS", "DEFAULT", "STATUS"], [[item["name"], item["vendor"], item["address"], "yes" if item["default"] else "—", item["status"]] for item in items])


@app.command("get")
def get(name: str, output: OutputOption = Format.table):
  """Show a registry and whether the platform reaches it."""
  registry = _call(lambda client: client.get_registry(name))
  if output == Format.json:
    print_json(registry)
    return
  _print(registry)


@app.command("set-default")
def set_default(name: str, output: OutputOption = Format.table):
  """Make a registry the default (platform-admins only)."""
  registry = _call(lambda client: client.set_default_registry(name))
  if output == Format.json:
    print_json(registry)
    return
  success(f"{name} is the default registry ({registry['address']})")


@app.command("remove")
def remove(name: str):
  """Remove a registry no version of the index is in (platform-admins only)."""
  _call(lambda client: client.remove_registry(name))
  success(f"registry {name} removed")
