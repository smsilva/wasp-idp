from enum import Enum

import typer

from ..bootstrap import local
from ..output import Format, OutputOption, fail, print_json, success


class Target(str, Enum):
  local = "local"
  azure = "azure"


def init(
  target: Target = typer.Option(..., help="Where the platform is installed."),
  output: OutputOption = Format.table,
):
  """Install the platform control plane (idempotent)."""
  if target != Target.local:
    fail(f"target '{target.value}' is not supported yet")
  try:
    result = local.install(log=None if output == Format.json else typer.echo)
  except local.BootstrapError as error:
    fail(str(error))
  if output == Format.json:
    print_json(result)
  else:
    success(f"Platform API at {result['api_url']} · config in {result['config']}")
