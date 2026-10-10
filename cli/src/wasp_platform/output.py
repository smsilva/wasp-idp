import json
from enum import Enum
from typing import Annotated

import typer


class Format(str, Enum):
  table = "table"
  json = "json"


OutputOption = Annotated[Format, typer.Option("--output", help="Output format.")]


def print_json(value) -> None:
  typer.echo(json.dumps(value, indent=2))


def print_table(headers: list[str], rows: list[list[str]]) -> None:
  widths = [max(len(str(cell)) for cell in column) for column in zip(headers, *rows)]
  for line in [headers, *rows]:
    typer.echo("  ".join(str(cell).ljust(width) for cell, width in zip(line, widths)).rstrip())


def success(message: str) -> None:
  typer.secho(f"✓ {message}", fg=typer.colors.GREEN)


def fail(message: str) -> None:
  typer.secho(f"✗ {message}", fg=typer.colors.RED, err=True)
  raise typer.Exit(1)
