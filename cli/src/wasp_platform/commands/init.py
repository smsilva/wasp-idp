import sys
from enum import Enum
from pathlib import Path

import typer

from ..bootstrap import local
from ..bootstrap.settings import SettingsError, check_admin, default_file, from_file, resolve, to_file
from ..bootstrap.timings import Timings, summary
from ..output import Format, OutputOption, fail, print_data, print_table, success


class Target(str, Enum):
  local = "local"
  azure = "azure"


def check_emails(values: list[str] | None) -> list[str]:
  try:
    return [check_admin(value) for value in values or []]
  except SettingsError as error:
    raise typer.BadParameter(str(error)) from None


def shown(value) -> str:
  if value in (None, []):
    return "—"
  if isinstance(value, list):
    return ", ".join(value)
  return str(value).lower() if isinstance(value, bool) else str(value)


def interactive() -> bool:
  return sys.stdin.isatty()


def init(
  target: Target = typer.Option(None, help="Where the platform is installed (default: local)."),
  admin: list[str] = typer.Option(None, callback=check_emails, help="E-mail that joins platform-admins on its first Google login; repeat it for more than one (remembered)."),
  aws_profile: str = typer.Option(None, "--aws-profile", help="AWS profile whose credential becomes the base of cloud accounts (remembered)."),
  with_crossplane: bool = typer.Option(None, "--with-crossplane", help="Install Crossplane, so environments can be created in cloud accounts; needs the base credential of --aws-profile (remembered)."),
  file: Path = typer.Option(None, "--file", help="Settings file to read, or to write with --generate-file (default: ~/.config/platform/init.yaml)."),
  generate_file: bool = typer.Option(False, "--generate-file", help="Write the settings to the file and install nothing."),
  force: bool = typer.Option(False, "--force", help="With --generate-file, overwrite an existing file."),
  yes: bool = typer.Option(False, "--yes", help="Install without asking."),
  dry_run: bool = typer.Option(False, "--dry-run", help="Show the settings and the steps init would run, and install nothing."),
  output: OutputOption = Format.table,
):
  """Install the platform control plane (idempotent)."""
  path = file or default_file()
  flags = {"target": target.value if target else None, "admins": admin, "aws_profile": aws_profile, "with_crossplane": with_crossplane}
  try:
    # --file must exist, unless init is about to write it; the default file is read only when present.
    values = from_file(path) if path.is_file() or (file and not generate_file) else {}
  except SettingsError as error:
    fail(str(error))
  settings = resolve(flags, values, str(path), local.remembered())

  if generate_file:
    if path.exists() and not force:
      fail(f"{path} already exists: edit it, or add --force to overwrite it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_file(settings))
    success(f"settings written to {path}: edit it, then run 'platform init'")
    return

  if settings["target"].value != Target.local.value:
    fail(f"target '{settings['target'].value}' is not supported yet")
  if dry_run:
    try:
      steps = local.planned_steps(settings["aws_profile"].value, settings["with_crossplane"].value)
    except local.BootstrapError as error:
      fail(str(error))
    if output.data:
      print_data({"settings": {name: {"value": setting.value, "source": setting.source} for name, setting in settings.items()}, "steps": steps}, output)
    else:
      print_settings(settings)
      typer.echo("\nsteps:")
      for step in steps:
        typer.echo(f"  {step}")
    return
  if not yes and (output.data or not interactive()):
    fail("add --yes to install without asking")
  # Shown even with --yes: a forgotten init.yaml must never apply unseen.
  if not output.data:
    print_settings(settings)
  if not yes and not typer.confirm("Proceed?", default=False):
    fail("nothing was installed")

  timings = Timings()
  try:
    result = local.install(
      admin_emails=settings["admins"].value,
      log=None if output.data else typer.echo,
      aws_profile=settings["aws_profile"].value,
      with_crossplane=settings["with_crossplane"].value,
      timings=timings,
    )
  except local.BootstrapError as error:
    if not output.data:
      print_timings(timings)
    fail(str(error))
  if output.data:
    print_data(result, output)
  else:
    print_timings(timings)
    success(f"Platform API at {result['api_url']} · config in {result['config']}")
    success(f"Keycloak issuer {result['issuer']}" + ("" if result["google"] else " (no Google login: set GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET)"))
    if result["cloud_account"]:
      success("cloud accounts verified by the aws_account provider" + (f" (base credential expires at {result['aws_base_expires']})" if result.get("aws_base_expires") else ""))
    if result.get("crossplane"):
      success("environments in cloud accounts provisioned through Crossplane (crossplane_aws provider)")


def print_settings(settings: dict) -> None:
  print_table(["SETTING", "VALUE", "SOURCE"], [[name, shown(setting.value), setting.source] for name, setting in settings.items()])


def print_timings(timings: Timings) -> None:
  """Where init spent its time (#442), so a slower provider or build shows up run after run."""
  typer.echo("\ntimings:")
  for line in summary(timings):
    typer.echo(f"  {line}")
