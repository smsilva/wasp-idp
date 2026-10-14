from enum import Enum

import typer

from ..bootstrap import local
from ..bootstrap.timings import Timings, summary
from ..output import Format, OutputOption, fail, print_json, success


class Target(str, Enum):
  local = "local"
  azure = "azure"


def init(
  target: Target = typer.Option(..., help="Where the platform is installed."),
  admin: str = typer.Option(None, help="E-mail that joins platform-admins on its first Google login (remembered)."),
  aws_profile: str = typer.Option(None, "--aws-profile", help="AWS profile whose credential becomes the base of cloud accounts (remembered)."),
  output: OutputOption = Format.table,
):
  """Install the platform control plane (idempotent)."""
  if target != Target.local:
    fail(f"target '{target.value}' is not supported yet")
  timings = Timings()
  try:
    result = local.install(admin_email=admin, log=None if output == Format.json else typer.echo, aws_profile=aws_profile, timings=timings)
  except local.BootstrapError as error:
    if output != Format.json:
      print_timings(timings)
    fail(str(error))
  if output == Format.json:
    print_json(result)
  else:
    print_timings(timings)
    success(f"Platform API at {result['api_url']} · config in {result['config']}")
    success(f"Keycloak issuer {result['issuer']}" + ("" if result["google"] else " (no Google login: set GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET)"))
    if result["cloud_account"]:
      success("cloud accounts verified by the aws_account provider" + (f" (base credential expires at {result['aws_base_expires']})" if result.get("aws_base_expires") else ""))


def print_timings(timings: Timings) -> None:
  """Where init spent its time (#442), so a slower provider or build shows up run after run."""
  typer.echo("\ntimings:")
  for line in summary(timings):
    typer.echo(f"  {line}")
