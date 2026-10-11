from enum import Enum

import typer

from ..bootstrap import local
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
  try:
    result = local.install(admin_email=admin, log=None if output == Format.json else typer.echo, aws_profile=aws_profile)
  except local.BootstrapError as error:
    fail(str(error))
  if output == Format.json:
    print_json(result)
  else:
    success(f"Platform API at {result['api_url']} · config in {result['config']}")
    success(f"Keycloak issuer {result['issuer']}" + ("" if result["google"] else " (no Google login: set GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET)"))
    if result["cloud_account"]:
      success("cloud accounts verified by the aws_account provider" + (f" (base credential expires at {result['aws_base_expires']})" if result.get("aws_base_expires") else ""))
