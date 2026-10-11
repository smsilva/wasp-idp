"""SCM connections (ADR 0025): the code platforms where the platform creates repos.

platform-admins only. On GitHub, `add` opens the browser on the API, which posts the App manifest to
GitHub; the private key goes from GitHub to the platform and never reaches this machine.
"""
import time
import webbrowser
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, print_table, success

app = typer.Typer(help="Connections with code platforms (platform-admins only).", no_args_is_help=True)
connection_app = typer.Typer(help="Connections with code platforms, such as a GitHub org.", no_args_is_help=True)
app.add_typer(connection_app, name="connection")

# Reasons the controller only leaves after someone changes the App or its installation.
NEEDS_ACTION = {"NotAllRepositories", "MissingPermissions", "InvalidCredentials", "CredentialMissing"}


class Vendor(str, Enum):
  github = "github"


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def _call(function, *args):
  try:
    return function(*args)
  except ApiError as error:
    fail(str(error))


def _poll(client: PlatformClient, name: str, done, timeout: int, quiet: bool) -> dict:
  deadline = time.monotonic() + timeout
  last = None
  while True:
    connection = _call(client.get_scm_connection, name)
    if done(connection):
      return connection
    if connection["status"] != last and not quiet:
      typer.echo(f"  {connection['status']}", err=True)
      last = connection["status"]
    if time.monotonic() > deadline:
      fail(f"{name}: still {connection['status']} after {timeout}s")
    time.sleep(2)


@connection_app.command("add")
def add(
  name: str,
  org: Annotated[str, typer.Option(help="GitHub organization login.")],
  vendor: Annotated[Vendor, typer.Option(help="Code platform.")] = Vendor.github,
  default: Annotated[bool, typer.Option("--default", help="Use this connection when none is named.")] = False,
  app_id: Annotated[int | None, typer.Option("--app-id", help="An App that already exists, instead of creating one in the browser.")] = None,
  private_key_file: Annotated[Path | None, typer.Option("--private-key-file", help="PEM key of the --app-id App; sent to the platform, which keeps it.")] = None,
  no_browser: Annotated[bool, typer.Option("--no-browser", help="Print the URL instead of opening the browser, and return without waiting.")] = False,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until the connection is ready.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait for the browser, and for ready with --wait.")] = 600,
  output: OutputOption = Format.table,
):
  """Connect the platform to a code platform (platform-admins only)."""
  if (app_id is None) != (private_key_file is None):
    fail("--app-id and --private-key-file go together")
  body = {"name": name, "vendor": vendor.value, "org": org, "default": default}
  if app_id is not None:
    try:
      body.update(appId=app_id, privateKeyPem=private_key_file.read_text())
    except OSError as error:
      fail(f"cannot read {private_key_file}: {error.strerror}")
  client = _client()
  quiet = output == Format.json
  connection = _call(client.create_scm_connection, body)
  if "next" in connection and no_browser:
    # The URL is single-use and valid for 10 minutes; `add` again issues a new one.
    if quiet:
      print_json(connection)
      return
    typer.echo(f"Open this URL to create the GitHub App \"{org}-platform\" (valid for 10 minutes):\n{connection['next']}")
    typer.echo(f"  then install it on the org and run: platform scm connection verify {name} --wait")
    return
  if "next" in connection:
    if not quiet:
      typer.echo(f'→ opening the browser to create the GitHub App "{org}-platform" …')
    if not webbrowser.open(connection["next"]):
      typer.echo(f"Open this URL to create the App:\n{connection['next']}", err=quiet)
    connection = _poll(client, name, lambda item: item["status"] != "AppNotCreated", timeout, quiet)
    if not quiet:
      success(f"app created (id {connection['appId']}) · private key stored by the platform")
  elif not quiet:
    success(f"connection {name} registered with App {app_id} · private key stored by the platform")
  if wait:
    connection = _wait_ready(client, name, timeout, quiet)
  if quiet:
    print_json(connection)
  else:
    _next_steps(connection)


def _wait_ready(client: PlatformClient, name: str, timeout: int, quiet: bool) -> dict:
  def done(connection: dict) -> bool:
    if connection["status"] == "ready":
      return True
    # A reason that needs a person settles nothing by waiting; NotInstalled is waited for.
    return not connection.get("verifying") and connection["status"] in NEEDS_ACTION

  connection = _poll(client, name, done, timeout, quiet)
  if connection["status"] != "ready":
    fail(f"{name}: {connection['status']}: {connection.get('message') or ''}".rstrip(": "))
  return connection


def _next_steps(connection: dict) -> None:
  name = connection["name"]
  if connection["status"] == "ready":
    success(f"{name} ready ({connection['org']}, all repositories)")
    return
  if connection.get("installUrl"):
    typer.echo(f"→ install it on the org: {connection['installUrl']}")
    typer.echo(f"  then run: platform scm connection verify {name} --wait")
  else:
    typer.echo(f"{name}: {connection['status']}")
    if connection.get("message"):
      typer.echo(f"  {connection['message']}")


@connection_app.command("list")
def list_(output: OutputOption = Format.table):
  """List connections."""
  items = _call(_client().list_scm_connections)
  if output == Format.json:
    print_json(items)
    return
  rows = [
    [item["name"], item["vendor"], item["org"] or "—", item["status"], "yes" if item["default"] else "", item.get("lastValidated") or "—"]
    for item in items
  ]
  print_table(["NAME", "VENDOR", "ORG", "STATUS", "DEFAULT", "VALIDATED"], rows)


@connection_app.command("get")
def get(name: str, output: OutputOption = Format.table):
  """Show a connection; never its credential."""
  connection = _call(_client().get_scm_connection, name)
  if output == Format.json:
    print_json(connection)
    return
  default = " (default)" if connection["default"] else ""
  typer.echo(f"{connection['name']}{default}: {connection['status']}")
  if connection.get("message"):
    typer.echo(f"  {connection['message']}")
  fields = [
    ("vendor", connection["vendor"]),
    ("org", connection["org"]),
    ("app", f"{connection['appSlug'] or '—'} (id {connection['appId']})" if connection.get("appId") else None),
    ("installation", connection.get("installationId")),
    ("repositories", connection.get("repositorySelection")),
    ("permissions", ", ".join(f"{key}:{value}" for key, value in sorted(connection["permissions"].items())) or None),
    ("validated", connection.get("lastValidated")),
    ("install", connection.get("installUrl")),
  ]
  for label, value in fields:
    if value is not None:
      typer.echo(f"  {label + ':':<14}{value}")


@connection_app.command("verify")
def verify(
  name: str,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until the connection is ready.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait with --wait.")] = 300,
  output: OutputOption = Format.table,
):
  """Ask the platform to check the App and its installation again."""
  client = _client()
  connection = _call(client.verify_scm_connection, name)
  if wait:
    connection = _wait_ready(client, name, timeout, output == Format.json)
  if output == Format.json:
    print_json(connection)
  elif wait:
    _next_steps(connection)
  else:
    typer.echo(f"verification of {name} requested: platform scm connection get {name}")


@connection_app.command("default")
def make_default(name: str, output: OutputOption = Format.table):
  """Make this the connection used when none is named."""
  connection = _call(_client().make_default_scm_connection, name)
  if output == Format.json:
    print_json(connection)
  else:
    success(f"{name} is the default connection")


@connection_app.command("remove")
def remove(name: str, output: OutputOption = Format.table):
  """Remove a connection and its credential; the App stays on GitHub."""
  result = _call(_client().delete_scm_connection, name)
  if output == Format.json:
    print_json(result)
    return
  success(f"connection {name} removed, with its private key")
  if result.get("appSettingsUrl"):
    typer.echo(f"  the GitHub App still exists; an org owner deletes it at {result['appSettingsUrl']} (Advanced → Delete GitHub App)")
