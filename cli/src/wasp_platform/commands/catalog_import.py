"""platform catalog import: Backstage catalog files into the platform catalog (#190).

The API computes the plan; this module only reads the files, shows the plan and asks.
"""
import json
import os
from pathlib import Path
from typing import Annotated

import typer
import yaml

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, print_table, success

PARENT_FIELDS = {"Domain": "parent", "System": "domain", "Resource": "system"}
SUFFIXES = (".yaml", ".yml")


class ImportFileError(Exception):
  pass


def _files(paths: list[Path]) -> list[Path]:
  found = []
  for path in paths:
    if path.is_dir():
      found += sorted(file for file in path.rglob("*") if file.is_file() and file.suffix in SUFFIXES)
    elif path.is_file():
      found.append(path)
    else:
      raise ImportFileError(f"{path}: no such file or directory")
  unique = {}
  for file in found:
    unique.setdefault(file.resolve(), file)
  return list(unique.values())


def _as_json(document, shown: str):
  """Dates and other YAML-only values travel as text; what JSON cannot carry at all fails here,
  naming the file, instead of as a traceback inside httpx."""
  try:
    return json.loads(json.dumps(document, default=str, allow_nan=False))
  except TypeError:
    raise ImportFileError(f"{shown}: keys must be text (quote dates and numbers used as keys)")
  except ValueError as error:
    raise ImportFileError(f"{shown}: not representable as JSON ({error})")


def read_documents(paths: list[Path]) -> list[dict]:
  """Every non-empty YAML document, with its source as `<path relative to cwd>#<position>`."""
  documents = []
  for file in _files(paths):
    shown = os.path.relpath(file)
    if shown.startswith(".."):
      # Outside the current folder, a chain of ../ says less than the absolute path.
      shown = str(file.resolve())
    try:
      loaded = [document for document in yaml.safe_load_all(file.read_text(encoding="utf-8")) if document is not None]
    except UnicodeDecodeError:
      raise ImportFileError(f"{shown}: not UTF-8")
    except yaml.YAMLError as error:
      mark = getattr(error, "problem_mark", None)
      line = f":{mark.line + 1}" if mark else ""
      raise ImportFileError(f"{shown}{line}: invalid YAML: {getattr(error, 'problem', None) or error}")
    for index, document in enumerate(loaded, 1):
      documents.append({"source": f"{shown}#{index}", "document": _as_json(document, shown)})
  if not documents:
    raise ImportFileError(f"no YAML documents found in {', '.join(str(path) for path in paths)}")
  return documents


def _value(value) -> str:
  return "—" if value is None else str(value)


def _detail(item: dict) -> str:
  action = item["action"]
  if item.get("failed"):
    return f"failed: {item['failed']}"
  if action == "create":
    field = PARENT_FIELDS.get(item["kind"])
    parent = (item.get("spec") or {}).get(field)
    return f"{field} {parent}" if parent else ""
  if action == "update":
    return "; ".join(f"{field}: {_value(old)} → {_value(new)}" for field, (old, new) in sorted(item["changes"].items()))
  if action == "skip":
    # Without a kind the row says nothing else about which file it is.
    return item["reason"] if item["kind"] else f"{item['reason']} ({item['source']})"
  if action == "forbidden":
    return f"{item['reason']} ({item['source']})"
  if action == "error":
    return f"{item['field']}: {item['reason']} ({item['source']})"
  return ""


def _action(item: dict) -> str:
  return item["action"] + (" ✓" if item.get("applied") else "") + (" ✗" if item.get("failed") else "")


def _print_plan(plan: dict) -> None:
  print_table(
    ["KIND", "NAME", "ACTION", "DETAIL"],
    [[_value(item["kind"]), _value(item["name"]), _action(item), _detail(item)] for item in plan["items"]],
  )
  summary = plan["summary"]
  parts = [f"{summary['create']} to create", f"{summary['update']} to update", f"{summary['unchanged']} unchanged", f"{summary['skip']} skipped"]
  if summary["forbidden"]:
    parts.append(f"{summary['forbidden']} forbidden")
  if summary["error"]:
    parts.append(f"{summary['error']} error" + ("s" if summary["error"] > 1 else ""))
  typer.echo("")
  typer.echo(", ".join(parts) + ".")


def _show(plan: dict, output: Format) -> None:
  print_json(plan) if output == Format.json else _print_plan(plan)


def import_catalog(
  paths: Annotated[list[Path], typer.Argument(help="Backstage catalog files or folders (recursive: *.yaml, *.yml).")],
  dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the plan and exit.")] = False,
  yes: Annotated[bool, typer.Option("--yes", help="Apply without asking.")] = False,
  output: OutputOption = Format.table,
):
  """Import Domains, Systems and Resources from Backstage catalog files, after reviewing the plan."""
  try:
    documents = read_documents(paths)
    client = PlatformClient()
    plan = client.import_catalog(documents, dry_run=True)
  except (ImportFileError, ApiError) as error:
    fail(str(error))
  summary = plan["summary"]
  blocked = summary["error"] + summary["forbidden"] > 0
  pending = summary["create"] + summary["update"] > 0
  # JSON is for machines: it never asks, so without --yes it is a dry run.
  if output == Format.json and (blocked or not pending or dry_run or not yes):
    print_json(plan)
    raise typer.Exit(1 if blocked else 0)
  if output == Format.table:
    _print_plan(plan)
    if blocked:
      fail("fix the errors above; nothing was applied")
    if not pending:
      typer.echo("nothing to do")
      return
    if dry_run:
      return
    if not yes and not typer.confirm("Apply?", default=False):
      typer.echo("nothing was applied")
      return
  try:
    result = client.import_catalog(documents, dry_run=False, plan_hash=None if yes else plan["planHash"])
  except ApiError as error:
    if error.plan:
      _show(error.plan, output)
    fail(str(error))
  if output == Format.json:
    print_json(result)
    return
  written = [item for item in result["items"] if item.get("applied")]
  created = sum(1 for item in written if item["action"] == "create")
  success(f"{created} created, {len(written) - created} updated")
