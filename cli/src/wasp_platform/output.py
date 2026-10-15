import json
import os
import sys
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


# The roles of the MkDocs terminal blocks (--t-* in platform/docs/stylesheets/extra.css, dark palette):
# change both together. Commands and plain arguments keep the terminal's own color, which reads on a
# light background too.
TERM_COLORS = {
  "opt": {"fg": (0x7C, 0xC4, 0xFF)},
  "val": {"fg": (0xE5, 0xC0, 0x7B)},
  "op": {"fg": (0x6B, 0x7A, 0x8D)},
  "comment": {"fg": (0x6B, 0x7A, 0x8D), "italic": True},
  "key": {"bold": True},
  "component": {"fg": (0x5E, 0xEA, 0xD4), "bold": True},
  "environment": {"fg": (0xC4, 0xA7, 0xFF), "bold": True},
}

# A value and its role: a key of TERM_COLORS, or None for a plain argument.
Term = tuple[str, str | None]


def _paint(text: str, role: str | None, color: bool) -> str:
  return typer.style(text, **TERM_COLORS[role]) if color and role else text


def _colored() -> bool:
  return sys.stderr.isatty() and not os.environ.get("NO_COLOR")


def next_steps(commands: list[tuple[str, Term | None, dict[str, Term]]]) -> None:
  """The ready-made commands for what was just shown (#454), on stderr so a pipe gets only the data: each
  is (command, argument, options), one option per line as in the scripts, a blank line between them."""
  color = _colored()
  lines = ["", _paint("next:", "comment", color)]
  for command, argument, options in commands:
    program, *words = command.split()
    head = " ".join([program, *(_paint(word, "key", color) for word in words)])
    if argument:
      head += " " + _paint(argument[0], argument[1], color)
    lines += ["", f"  {head}"]
    for option, (value, role) in options.items():
      lines[-1] += " " + _paint("\\", "op", color)
      lines.append(f"    {_paint(option, 'opt', color)} {_paint(value, role or 'val', color)}")
  for line in lines:
    typer.echo(line, err=True)


def drop_empty(value):
  """--hide-empty on data output: keys whose value is null, an empty string or an empty list go away."""
  if isinstance(value, dict):
    return {key: drop_empty(item) for key, item in value.items() if item not in (None, "", [], {})}
  if isinstance(value, list):
    return [drop_empty(item) for item in value]
  return value
