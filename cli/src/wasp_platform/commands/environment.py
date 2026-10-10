import time
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, print_table, success

app = typer.Typer(help="Environments where releases run.", no_args_is_help=True)

FAILED = {"ProvisioningFailed"}


class Profile(str, Enum):
  ephemeral = "ephemeral"
  shared = "shared"


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def remaining(expires_at: str | None, now: datetime | None = None) -> str:
  if not expires_at:
    return "—"
  now = now or datetime.now(timezone.utc)
  seconds = int((datetime.fromisoformat(expires_at.replace("Z", "+00:00")) - now).total_seconds())
  if seconds <= 0:
    return "expired"
  days, rest = divmod(seconds, 86400)
  hours, rest = divmod(rest, 3600)
  minutes = rest // 60
  parts = [f"{days}d" if days else "", f"{hours}h" if hours else "", f"{minutes}m" if minutes and not days else ""]
  return " ".join(part for part in parts if part) or "<1m"


@app.command("create")
def create(
  name: str,
  profile: Annotated[Profile, typer.Option(help="Kind of environment; the platform decides where it runs.")],
  expires: Annotated[str | None, typer.Option(help="Lifetime such as 30m, 12h, 3d or 1w.")] = None,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until the environment is ready.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait with --wait.")] = 600,
  output: OutputOption = Format.table,
):
  """Create an environment."""
  client = _client()
  try:
    environment = client.create_environment(name, profile.value, expires)
    if output == Format.table:
      typer.echo(f"provisioning {name} (profile: {profile.value}) …")
    if wait:
      environment = _wait_ready(client, environment, timeout, quiet=output == Format.json)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(environment)
  elif environment["status"] == "ready":
    success(f"{name} ready")
  else:
    typer.echo(f"{name}: {environment['status']}")


def _wait_ready(client: PlatformClient, environment: dict, timeout: int, quiet: bool) -> dict:
  deadline = time.monotonic() + timeout
  last = None
  while environment["status"] != "ready":
    if environment["status"] != last and not quiet:
      typer.echo(f"  {environment['status']}", err=True)
      last = environment["status"]
    if environment["status"] in FAILED:
      fail(f"{environment['name']}: {environment.get('message') or environment['status']}")
    if time.monotonic() > deadline:
      fail(f"{environment['name']} not ready after {timeout}s (status: {environment['status']})")
    time.sleep(2)
    environment = client.get_environment(environment["name"])
  return environment


@app.command("list")
def list_(output: OutputOption = Format.table):
  """List environments."""
  try:
    items = _client().list_environments()
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(items)
    return
  rows = [[item["name"], item["profile"], item["status"], remaining(item.get("expiresAt"))] for item in items]
  print_table(["NAME", "PROFILE", "STATUS", "EXPIRES"], rows)


@app.command("delete")
def delete(name: str, output: OutputOption = Format.table):
  """Delete an environment."""
  try:
    result = _client().delete_environment(name)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(result)
  else:
    success(f"{name} deleting")
