"""The Score gate (#291): what an app-spec.yaml must pass to become a Workload Spec (ADR 0033)."""
import json
from dataclasses import dataclass, field
from functools import cache
from importlib import resources as package_files
from typing import Callable

import jsonschema
import yaml

APP_SPEC = "app-spec.yaml"
# Resource types the platform provisions today.
RESOURCE_TYPES = ("postgres", "dns", "route")


@cache
def score_schema() -> dict:
  """score.dev/v1b1, vendored from score-spec/spec: never fetched at run time."""
  return json.loads(package_files.files(__package__).joinpath("schemas/score-v1b1.json").read_text(encoding="utf-8"))


class _Loader(yaml.SafeLoader):
  """safe_load without aliases: a few hundred bytes of nested aliases expand to millions of nodes in
  whatever walks the document (the schema, json.dumps, the kube API). A Score never needs them."""

  def compose_node(self, parent, index):
    if self.check_event(yaml.AliasEvent):
      event = self.peek_event()
      raise yaml.composer.ComposerError(None, None, f"aliases are not accepted (*{event.anchor})", event.start_mark)
    return super().compose_node(parent, index)


def load(text: str):
  return yaml.load(text, Loader=_Loader)


@dataclass
class Check:
  """The document, the errors (each a field and a reason) and the resources it declares."""

  document: object = None
  errors: list[dict] = field(default_factory=list)
  resources: list[dict] = field(default_factory=list)

  @property
  def valid(self) -> bool:
    return not self.errors


def check(text: str, resource_exists: Callable[[str], bool], resource_types=RESOURCE_TYPES) -> Check:
  try:
    document = load(text)
  except yaml.YAMLError as error:
    return Check(errors=[{"field": APP_SPEC, "reason": f"not valid YAML: {error}"}])
  errors = []
  for error in sorted(jsonschema.Draft202012Validator(score_schema()).iter_errors(document), key=lambda item: list(map(str, item.absolute_path))):
    path = ".".join(str(part) for part in error.absolute_path) or "(root)"
    errors.append({"field": path, "reason": error.message[:300]})
  resources = document.get("resources") if isinstance(document, dict) else None
  declared = []
  for name, item in resources.items() if isinstance(resources, dict) else ():
    if not isinstance(item, dict) or not isinstance(item.get("type"), str):
      continue
    declared.append({"name": str(name), "type": item["type"]})
    if item["type"] not in resource_types:
      errors.append({"field": f"resources.{name}.type", "reason": f"'{item['type']}' is not a resource type of the platform ({', '.join(resource_types)})"})
    if isinstance(item.get("id"), str) and not resource_exists(item["id"]):
      errors.append({"field": f"resources.{name}.id", "reason": f"resource '{item['id']}' is not in the catalog"})
  if not errors:
    # The document is stored in the Version as JSON: a YAML date or a non-string key would not survive.
    try:
      json.dumps(document, allow_nan=False)
    except (TypeError, ValueError) as error:
      errors.append({"field": APP_SPEC, "reason": f"not representable as JSON: {error}"})
  return Check(document, errors, declared)
