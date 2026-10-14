import json
from enum import Enum
from typing import Annotated

import typer
import yaml
from rich.console import Console
from rich.syntax import Syntax


class Format(str, Enum):
  table = "table"
  json = "json"
  jsonc = "jsonc"
  yaml = "yaml"
  yamlc = "yamlc"

  @property
  def data(self) -> bool:
    """Every format but table is for machines: no progress, no prompts."""
    return self != Format.table


OutputOption = Annotated[Format, typer.Option("--output", "-o", help="Output format; jsonc and yamlc are colored.")]


class _Dumper(yaml.SafeDumper):
  pass


def _string(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
  # Multi-line values (kubeconfigs, PEMs) read as blocks, not as one escaped line.
  return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


_Dumper.add_representer(str, _string)


def to_yaml(value) -> str:
  return yaml.dump(value, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=float("inf"))


def _console() -> Console:
  # Color was asked for by name, so it survives a pipe (`| less -R`); NO_COLOR still turns it off.
  return Console(force_terminal=True, soft_wrap=True)


def print_json(value) -> None:
  typer.echo(json.dumps(value, indent=2))


def print_data(value, output: Format) -> None:
  if output == Format.jsonc:
    _console().print_json(data=value, indent=2)
  elif output == Format.yaml:
    typer.echo(to_yaml(value), nl=False)
  elif output == Format.yamlc:
    _console().print(Syntax(to_yaml(value).rstrip("\n"), "yaml", theme="ansi_dark", background_color="default"))
  else:
    print_json(value)


def examples(*commands: str) -> str:
  """The epilog of a command's --help: real invocations, one per line (#408)."""
  return "Examples:\n\n" + "\n".join(f"  $ {command}" for command in commands)


def print_table(headers: list[str], rows: list[list[str]]) -> None:
  widths = [max(len(str(cell)) for cell in column) for column in zip(headers, *rows)]
  for line in [headers, *rows]:
    typer.echo("  ".join(str(cell).ljust(width) for cell, width in zip(line, widths)).rstrip())


def success(message: str) -> None:
  typer.secho(f"✓ {message}", fg=typer.colors.GREEN)


def fail(message: str) -> None:
  typer.secho(f"✗ {message}", fg=typer.colors.RED, err=True)
  raise typer.Exit(1)
