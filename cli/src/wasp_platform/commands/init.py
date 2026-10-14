import os
import shlex
import shutil
import subprocess
import sys
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console

from .. import config
from ..bootstrap import local
from ..bootstrap.reporters import LiveReporter, LogReporter, PlainReporter, previous_run, settings_card
from ..bootstrap.settings import SettingsError, check_admin, default_file, from_file, resolve, to_file
from ..bootstrap.tasks import Reporter, Reporters
from ..bootstrap.timings import Timings, summary
from ..output import Format, OutputOption, fail, print_data, print_table, success


class Target(str, Enum):
  local = "local"
  azure = "azure"


class Progress(str, Enum):
  auto = "auto"
  live = "live"
  plain = "plain"


# Lines of the failing step's log shown when init fails: the end of what it ran.
FAILURE_TAIL = 30
# Where --edit finds the editor, first set wins: the CLI's own, as KUBE_EDITOR is kubectl's, then the usual ones.
EDITOR_VARIABLES = ("PLATFORM_EDITOR", "VISUAL", "EDITOR")


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


def editor_variable() -> str | None:
  return next((name for name in EDITOR_VARIABLES if os.environ.get(name, "").strip()), None)


def editor_command() -> list[str]:
  """The editor for --edit: the first variable set, else VS Code when on the PATH (--wait, so init reads
  the file once the tab closes), else vi."""
  variable = editor_variable()
  if variable:
    return shlex.split(os.environ[variable])
  return ["code", "--wait"] if shutil.which("code") else ["vi"]


def init(
  target: Target = typer.Option(None, help="Where the platform is installed (default: local)."),
  admin: list[str] = typer.Option(None, callback=check_emails, help="E-mail that joins platform-admins on its first Google login; repeat it for more than one (remembered)."),
  aws_profile: str = typer.Option(None, "--aws-profile", help="AWS profile whose credential becomes the base of cloud accounts (remembered)."),
  with_crossplane: bool = typer.Option(None, "--with-crossplane", help="Install Crossplane, so environments can be created in cloud accounts; needs the base credential of --aws-profile (remembered)."),
  file: Path = typer.Option(None, "--file", help="Settings file to read, or to write with --generate-file (default: ~/.config/platform/init.yaml)."),
  generate_file: bool = typer.Option(False, "--generate-file", help="Write the settings to the file and install nothing."),
  edit: bool = typer.Option(False, "--edit", help="Open the settings file in $PLATFORM_EDITOR, $VISUAL or $EDITOR (else VS Code, else vi), writing it first when missing, and install nothing."),
  force: bool = typer.Option(False, "--force", help="With --generate-file, overwrite an existing file."),
  yes: bool = typer.Option(False, "--yes", help="Install without asking."),
  dry_run: bool = typer.Option(False, "--dry-run", help="Show the settings and the steps init would run, and install nothing."),
  progress: Progress = typer.Option(Progress.auto, "--progress", help="How the steps are shown while init runs: live is a card that redraws, plain is one line per step with a heartbeat; auto is live on a terminal, plain otherwise."),
  output: OutputOption = Format.table,
):
  """Install the platform control plane (idempotent)."""
  path = file or default_file()
  if edit:
    others = [name for name, given in (("--generate-file", generate_file), ("--dry-run", dry_run), ("--yes", yes), ("--output", output.data)) if given]
    if others:
      fail(f"--edit installs nothing: drop {', '.join(others)}")
    if not interactive() and not editor_variable():
      fail(f"--edit needs a terminal, or an editor in {', '.join(EDITOR_VARIABLES)}")
  flags = {"target": target.value if target else None, "admins": admin, "aws_profile": aws_profile, "with_crossplane": with_crossplane}
  try:
    # --file must exist, unless init is about to write it; the default file is read only when present.
    values = from_file(path) if path.is_file() or (file and not generate_file and not edit) else {}
  except SettingsError as error:
    fail(str(error))
  settings = resolve(flags, values, str(path), local.remembered())

  if edit:
    edit_file(path, settings)
    return

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
  console = Console(highlight=False)
  live = not output.data and wants_live(progress, console)
  rows = [(name, shown(setting.value), setting.source) for name, setting in settings.items()]
  # Shown even with --yes: a forgotten init.yaml must never apply unseen. The live card shows them itself.
  if not output.data and not (live and yes):
    if live:
      console.print(settings_card(console, rows))
    else:
      print_settings(settings)
  if not yes:
    if not typer.confirm("Proceed?", default=False):
      fail("nothing was installed")
    if live:
      # The card redraws from here with the settings at its top: one card, not a copy above it.
      erase(console, len(console.render_lines(settings_card(console, rows), pad=False)) + 1)

  timings = Timings()
  base = config.state_dir() / "init"
  previous = previous_run(base)
  record = LogReporter(base, {name: {"value": setting.value, "source": setting.source} for name, setting in settings.items()})
  if output.data:
    terminal = Reporter()
  elif live:
    terminal = LiveReporter(console, record.folder, previous, f"{settings['target'].value} · run {record.folder.name}", rows)
  else:
    terminal = PlainReporter(typer.echo)
  try:
    result = local.install(
      admin_emails=settings["admins"].value,
      reporter=Reporters(record, terminal),
      aws_profile=settings["aws_profile"].value,
      with_crossplane=settings["with_crossplane"].value,
      timings=timings,
    )
  except BaseException as error:
    terminal.close()
    record.close(error)
    if isinstance(error, local.BootstrapError):
      if not output.data:
        if not live:
          print_timings(timings)
        print_failure(record)
      fail(str(error))
    raise
  terminal.close()
  record.close()
  result["logs"] = str(record.folder)
  if output.data:
    print_data(result, output)
  else:
    if not live:
      print_timings(timings)
      typer.echo(f"\nlogs in {record.folder}")
    success(f"Platform API at {result['api_url']} · config in {result['config']}")
    success(f"Keycloak issuer {result['issuer']}" + ("" if result["google"] else " (no Google login: set GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET)"))
    if result["cloud_account"]:
      success("cloud accounts verified by the aws_account provider" + (f" (base credential expires at {result['aws_base_expires']})" if result.get("aws_base_expires") else ""))
    if result.get("crossplane"):
      success("environments in cloud accounts provisioned through Crossplane (crossplane_aws provider)")


def edit_file(path: Path, settings: dict) -> None:
  """Opens the settings file, as `git config --edit` does; a missing one is written first. Read back with
  the rules of --file, so a mistake shows now and not halfway through an install."""
  if not path.exists():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_file(settings))
  command = editor_command()
  try:
    subprocess.run([*command, str(path)], check=True)
  except FileNotFoundError:
    fail(f"editor '{command[0]}' not found: set {EDITOR_VARIABLES[0]}")
  except subprocess.CalledProcessError as error:
    fail(f"the editor exited with {error.returncode}")
  try:
    from_file(path)
  except SettingsError as error:
    fail(f"{error} (run 'platform init --edit' again)")
  success(f"settings saved in {path}: run 'platform init --dry-run'")


def wants_live(progress: Progress, console: Console) -> bool:
  """The card needs a terminal that redraws in place; CI, a pipe and cli-smoke get plain lines."""
  return progress == Progress.live or (progress == Progress.auto and console.is_terminal and not console.is_dumb_terminal)


def erase(console: Console, lines: int) -> None:
  """Moves the cursor up over the last lines and clears them."""
  if console.is_terminal:
    console.file.write(f"\x1b[{lines}A\r\x1b[0J")
    console.file.flush()


def print_settings(settings: dict) -> None:
  print_table(["SETTING", "VALUE", "SOURCE"], [[name, shown(setting.value), setting.source] for name, setting in settings.items()])


def print_timings(timings: Timings) -> None:
  """Where init spent its time (#442), so a slower provider or build shows up run after run."""
  typer.echo("\ntimings:")
  for line in summary(timings):
    typer.echo(f"  {line}")


def print_failure(record: LogReporter) -> None:
  """The end of the failing step's log, and where the whole run is."""
  path = record.file_of(record.failed_step) if record.failed_step else None
  if path and path.is_file():
    typer.echo(f"\nlast lines of {path}:")
    for line in path.read_text(encoding="utf-8").splitlines()[-FAILURE_TAIL:]:
      typer.echo(f"  {line}")
  typer.echo(f"\nlogs in {record.folder}")
