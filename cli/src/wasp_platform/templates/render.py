"""Renders a component template (ADR 0024).

Jinja2 with the delimiters of the Backstage scaffolder (`${{ … }}`) and its `dump` filter, so
Backstage templates render without rewriting. Shared by `platform catalog template render` and,
later, by the service behind `component create`.
"""
import fnmatch
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import jinja2
import jinja2.sandbox
import yaml

DEFINITION = "template.yaml"
CONTENT = "content"
CATALOG_INFO = "catalog-info.yaml"
ORIGIN_ANNOTATION = "platform.wasp.silvios.me/template"


class RenderError(Exception):
  pass


@dataclass
class Template:
  """A template in the platform format: template.yaml next to a content/ folder."""
  name: str
  type: str
  content: Path
  description: str | None = None
  parameters: dict = field(default_factory=dict)
  copy_without_rendering: list[str] = field(default_factory=list)

  def defaults(self) -> dict:
    return {
      key: schema["default"]
      for key, schema in (self.parameters.get("properties") or {}).items()
      if isinstance(schema, dict) and "default" in schema
    }


def load_template(folder: Path) -> Template:
  definition = folder / DEFINITION
  try:
    data = yaml.safe_load(definition.read_text(encoding="utf-8"))
  except FileNotFoundError:
    raise RenderError(f"{folder}: no {DEFINITION}")
  except yaml.YAMLError as error:
    raise RenderError(f"{definition}: invalid YAML: {error}")
  if not isinstance(data, dict) or not data.get("name") or not data.get("type"):
    raise RenderError(f"{definition}: 'name' and 'type' are required")
  content = folder / CONTENT
  if not content.is_dir():
    raise RenderError(f"{folder}: no {CONTENT}/ folder")
  return Template(
    name=data["name"],
    type=data["type"],
    content=content,
    description=data.get("description"),
    parameters=data.get("parameters") or {},
    copy_without_rendering=list(data.get("copyWithoutRendering") or []),
  )


def _environment() -> jinja2.Environment:
  # Sandboxed: a registered template comes from another repo and renders on the caller's machine.
  environment = jinja2.sandbox.ImmutableSandboxedEnvironment(
    variable_start_string="${{",
    variable_end_string="}}",
    undefined=jinja2.StrictUndefined,
    keep_trailing_newline=True,
    autoescape=False,
  )
  environment.filters["dump"] = lambda value: json.dumps(value)
  return environment


def _render_text(environment: jinja2.Environment, text: str, values: dict, shown: str) -> str:
  try:
    return environment.from_string(text).render(values=values)
  except jinja2.TemplateSyntaxError as error:
    raise RenderError(f"{shown}:{error.lineno}: {error.message}")
  except Exception as error:
    # Undefined values, the sandbox, and runtime errors of the template itself (1 + 'x').
    raise RenderError(f"{shown}: {error}")


def _files(source: Path) -> list[Path]:
  """Every file of the content, without following links: a fetched template must not pull files from
  outside it (a link to ~/.ssh) into the result."""
  found = []
  for folder, folders, files in os.walk(source, followlinks=False):
    for name in [*folders, *files]:
      path = Path(folder) / name
      if path.is_symlink():
        raise RenderError(f"{path.relative_to(source).as_posix()}: symlinks are not allowed in template content")
    found += [Path(folder) / name for name in files]
  return sorted(found)


def _inside(output: Path, rendered: str, shown: str) -> Path:
  """A rendered file name, refused when a value (such as ../x) moves it out of output."""
  target = (output / rendered).resolve()
  if rendered.startswith("/") or not target.is_relative_to(output.resolve()):
    raise RenderError(f"{shown}: renders to '{rendered}', outside the output folder")
  return target


def _literal(relative: str, patterns: list[str]) -> bool:
  return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def render(source: Path, output: Path, values: dict, copy_without_rendering: list[str] | None = None) -> list[Path]:
  """Renders every file of source into output, which must not exist yet; returns the files written."""
  patterns = copy_without_rendering or []
  if output.exists():
    raise RenderError(f"{output} already exists")
  environment = _environment()
  written = []
  try:
    for file in _files(source):
      relative = file.relative_to(source).as_posix()
      target = _inside(output, _render_text(environment, relative, values, relative), relative)
      target.parent.mkdir(parents=True, exist_ok=True)
      if _literal(relative, patterns):
        shutil.copyfile(file, target)
      else:
        try:
          text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
          # Binary files (images, fonts) are content, never templates.
          shutil.copyfile(file, target)
        else:
          target.write_text(_render_text(environment, text, values, relative), encoding="utf-8")
      shutil.copymode(file, target)
      written.append(target)
  except RenderError:
    shutil.rmtree(output, ignore_errors=True)
    raise
  return written


def annotate_origin(output: Path, origin: str) -> None:
  """Records `<template>@<ref>` in the generated catalog-info.yaml. The platform writes it, not the
  template, so imported Backstage templates get it too (ADR 0024)."""
  path = output / CATALOG_INFO
  if not path.is_file():
    return
  documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
  for document in documents:
    if isinstance(document, dict) and document.get("kind") == "Component":
      metadata = document.setdefault("metadata", {})
      metadata.setdefault("annotations", {})[ORIGIN_ANNOTATION] = origin
  path.write_text(yaml.safe_dump_all(documents, sort_keys=False, allow_unicode=True), encoding="utf-8")
