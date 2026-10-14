"""platform status (#269): each capability of the platform, who implements it and whether it works.

The API computes it (ADR 0039); the CLI only lays it out. platform-admins get the drivers, the detail
and the fix; everyone else, the name and the status.
"""
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_data, print_table, success

ACTIVE, NO_PROVIDER = "Active", "NoProviderForCapability"


def _failing(items: list[dict]) -> list[dict]:
  """Installed and not Active: what makes the exit code 1. A capability not installed is no failure."""
  return [item for item in items if item["status"] not in (ACTIVE, NO_PROVIDER)]


def _table(headers: list[str], rows: list[list[str]], indent: str = "  ") -> None:
  widths = [max(len(str(cell)) for cell in column) for column in zip(headers, *rows)]
  for line in [headers, *rows]:
    typer.echo(indent + "  ".join(str(cell).ljust(width) for cell, width in zip(line, widths)).rstrip())


def _field(name: str, value) -> None:
  typer.echo(f"  {name.ljust(13)} {value}")


def _block(item: dict) -> None:
  """One capability in full: what `status <capability>` and `status --verbose` print."""
  typer.echo(f"{item['name']}  {item['status']}")
  if "drivers" not in item:
    if item["status"] not in (ACTIVE, NO_PROVIDER):
      typer.echo("  ask a platform-admin to configure it")
    return
  if item["dependsOn"]:
    _field("depends on", ", ".join(item["dependsOn"]))
  if item.get("detail"):
    _field("detail", item["detail"])
  if item.get("fix"):
    _field("fix", item["fix"])
  drivers = item["drivers"]
  if drivers:
    vendors = any(driver.get("vendor") for driver in drivers)
    base = item["name"] == "cloud-account"
    headers = [*(["DRIVER"] if vendors else []), "PROVIDER", "VERSION", "REPLICAS", *(["BASE IDENTITY"] if base else []), "STATUS"]
    rows = [
      [
        *([driver.get("vendor") or "—"] if vendors else []),
        driver["provider"], driver["version"], f"{driver['replicas']['ready']}/{driver['replicas']['desired']}",
        *([driver.get("baseIdentity") or "—"] if base else []),
        driver["status"],
      ]
      for driver in drivers
    ]
    typer.echo()
    _table(headers, rows)
  if item.get("connections"):
    typer.echo()
    _table(
      ["CONNECTION", "VENDOR", "ORG", "STATUS"],
      [
        [
          connection["name"] + (" (default)" if connection["default"] else ""), connection["vendor"] or "—", connection["org"] or "—",
          "Ready" if connection["status"] == "ready" else ": ".join(part for part in (connection["status"], connection.get("message")) if part),
        ]
        for connection in item["connections"]
      ],
    )
  if item.get("registries"):
    typer.echo()
    _table(
      ["REGISTRY", "VENDOR", "ADDRESS", "STATUS"],
      [
        [
          registry["name"] + (" (default)" if registry["default"] else ""), registry["vendor"] or "—", registry["address"] or "—",
          "Ready" if registry["status"] == "ready" else ": ".join(part for part in (registry["status"], registry.get("message")) if part),
        ]
        for registry in item["registries"]
      ],
    )
  if item.get("accounts"):
    typer.echo()
    _table(
      ["ACCOUNTS", "READY", "NOT READY"],
      [
        [account["vendor"], str(account["ready"]), ", ".join(f"{count} ({state})" for state, count in sorted(account["notReady"].items())) or "—"]
        for account in item["accounts"]
      ],
    )
    typer.echo()
    typer.echo("  accounts by owner: platform cloud account list")


def _summary(items: list[dict], admin: bool) -> None:
  failing = _failing(items)
  absent = [item["name"] for item in items if item["status"] == NO_PROVIDER]
  installed = len(items) - len(absent)
  if failing:
    names = ", ".join(item["name"] for item in failing)
    typer.secho(f"✗ {len(failing)} of {installed} installed capabilities not Active: {names}", fg=typer.colors.RED, err=True)
    hint = "details and the fix: platform status <capability>" if admin else "ask a platform-admin to configure them"
    typer.secho(f"  {hint}", err=True)
    return
  if absent:
    success(f"all {installed} installed capabilities Active ({len(absent)} not installed: {', '.join(absent)})")
  else:
    success(f"all {installed} capabilities Active")


def status(
  capability: Annotated[str | None, typer.Argument(help="One capability, in full: its drivers and what they serve.")] = None,
  verbose: Annotated[bool, typer.Option("--verbose", help="Every capability in full.")] = False,
  output: OutputOption = Format.table,
):
  """Each capability of the platform: who implements it and whether it works. Exits 1 when an installed one is not Active."""
  try:
    client = PlatformClient()
    items = [client.get_capability(capability)] if capability else client.list_capabilities()
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(items[0] if capability else {"items": items}, output)
  elif capability or verbose:
    for index, item in enumerate(items):
      if index:
        typer.echo()
      _block(item)
    if verbose:
      typer.echo()
      _summary(items, "drivers" in items[0])
  else:
    admin = "drivers" in items[0]
    if admin:
      print_table(
        ["CAPABILITY", "STATUS", "PROVIDERS", "DETAIL"],
        [[item["name"], item["status"], ", ".join(item["providers"]) or "—", item.get("detail") or "—"] for item in items],
      )
    else:
      print_table(["CAPABILITY", "STATUS"], [[item["name"], item["status"]] for item in items])
    _summary(items, admin)
  if _failing(items):
    raise typer.Exit(1)
