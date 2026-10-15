"""platform registry: the OCI registries a build pushes to (ADR 0037, #365).

platform-admins add them, anyone signed in lists them and picks one in `build create --registry`. At
most one is the default, the registry of a build without --registry. `--scm-connection` fills a ghcr
registry from a github connection: GHCR of the connection's org, pushed by the CI of its repos.
"""
from enum import Enum
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, HideEmptyOption, OutputOption, examples, fail, hiding, next_steps, print_data, print_fields, print_table, success

app = typer.Typer(help="OCI registries: where builds push images (and, later, Helm charts and other OCI artifacts).", no_args_is_help=True)


class Vendor(str, Enum):
  ghcr = "ghcr"

RegistryName = Annotated[str, typer.Argument(help="Registry name (platform registry list).")]


def _call(function, *args):
  try:
    return function(PlatformClient(), *args)
  except ApiError as error:
    fail(str(error))


def _print(registry: dict, hide_empty: bool = False) -> None:
  typer.echo(f"{registry['name']}: {registry['status']}" + (f" — {registry['message']}" if registry.get("message") else ""))
  print_fields([
    ("vendor", registry.get("vendor")),
    ("address", registry.get("address")),
    ("default", "yes" if registry.get("default") else "no"),
    ("pull", registry.get("pullMode")),
  ], hide_empty, width=9)


@app.command("add", epilog=examples("platform registry add ghcr-wasp-foundry --scm-connection wasp-foundry --default", "platform registry add ghcr-wasp-foundry --vendor ghcr --namespace wasp-foundry"))
def add(
  name: Annotated[str, typer.Argument(help="Name for the new registry, such as ghcr-wasp-foundry.")],
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
  if output.data:
    print_data(registry, output)
    return
  success(f"registry {name} added{' (default)' if registry['default'] else ''} · {registry['address']}, pushed by the CI of {registry['namespace']} repos")


@app.command("list", epilog=examples("platform registry list", "platform registry list --output json"))
def list_(output: OutputOption = Format.table):
  """List the registries: NAME, VENDOR, ADDRESS, DEFAULT, STATUS."""
  items = _call(lambda client: client.list_registries())
  if output.data:
    print_data(items, output)
    return
  print_table(["NAME", "VENDOR", "ADDRESS", "DEFAULT", "STATUS"], [[item["name"], item["vendor"], item["address"], "yes" if item["default"] else "—", item["status"]] for item in items])


@app.command("get", epilog=examples("platform registry get ghcr-wasp-foundry", "platform registry get ghcr-wasp-foundry --hide-empty --output json"))
def get(name: RegistryName, hide_empty: HideEmptyOption = None, output: OutputOption = Format.table):
  """Show a registry and whether the platform reaches it."""
  hide_empty = hiding(hide_empty)
  registry = _call(lambda client: client.get_registry(name))
  if output.data:
    print_data(registry, output, hide_empty)
    return
  _print(registry, hide_empty)
  steps = [] if registry.get("default") else [("platform registry set-default", (registry["name"], "key"), {})]
  steps.append(("platform build create", None, {"--component": ("<component>", "component"), "--branch": ("<branch>", None), "--registry": (registry["name"], "key")}))
  next_steps(steps)


@app.command("set-default", epilog=examples("platform registry set-default ghcr-wasp-foundry"))
def set_default(name: RegistryName, output: OutputOption = Format.table):
  """Make a registry the default (platform-admins only)."""
  registry = _call(lambda client: client.set_default_registry(name))
  if output.data:
    print_data(registry, output)
    return
  success(f"{name} is the default registry ({registry['address']})")


@app.command("remove", epilog=examples("platform registry remove ghcr-wasp-foundry"))
def remove(name: RegistryName):
  """Remove a registry no version of the index is in (platform-admins only)."""
  _call(lambda client: client.remove_registry(name))
  success(f"registry {name} removed")
