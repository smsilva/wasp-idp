"""Conversion of Backstage and platform-format templates into the Template spec (ADR 0024)."""
from pathlib import Path

import pytest
import yaml

from platform_api.templates import Invalid, content_folders, convert_backstage, convert_platform, flatten

REPO = Path(__file__).parents[3]
ORIGIN = {"repo": "https://github.com/smsilva/wasp-idp", "ref": "main"}


def backstage(**spec):
  return {
    "apiVersion": "scaffolder.backstage.io/v1beta3",
    "kind": "Template",
    "metadata": {"name": "python-service", "description": "FastAPI"},
    "spec": {"owner": "group:default/guests", "type": "service", **spec},
  }


def test_the_repo_backstage_template():
  document = yaml.safe_load((REPO / "idp/templates/python-service/template.yaml").read_text())
  name, spec, steps = convert_backstage(document, "idp/templates/python-service/template.yaml", ORIGIN)
  assert name == "python-service"
  assert spec == {
    "type": "service",
    "source": {"repo": ORIGIN["repo"], "path": "idp/templates/python-service/content", "ref": "main"},
    "parameters": {},
    "copyWithoutRendering": [".github/workflows/*"],
    "description": "Creates a FastAPI service in the wasp-foundry GitHub org, with CI to GHCR and deployment to the development and production k3d clusters via GitOps.",
    "owner": "guests",
  }
  assert steps == [
    ("publish", "publish:github", "the platform creates the repo"),
    ("fetch-gitops", "fetch:template", "renders outside the repo content (targetPath)"),
    ("gitops-pr", "publish:github:pull-request", "GitOps belongs to the release"),
    ("register", "catalog:register", "the platform discovery finds catalog-info.yaml"),
  ]
  assert content_folders(document, "idp/templates/python-service/template.yaml") == ["idp/templates/python-service/content", "idp/templates/python-service/gitops"]


def test_parameter_pages_merge_into_one_schema_without_platform_fields():
  document = backstage(
    parameters=[
      {"title": "Service", "required": ["name", "port"], "properties": {"name": {"type": "string"}, "port": {"type": "integer", "default": 8080, "ui:widget": "updown"}}},
      {"title": "Extra", "properties": {"owner": {"type": "string"}, "tier": {"type": "string", "enum": ["a", "b"]}}},
    ],
    steps=[{"id": "fetch", "action": "fetch:template", "input": {"url": "./skeleton"}}],
  )
  _, spec, _ = convert_backstage(document, "t/template.yaml", ORIGIN)
  assert spec["parameters"] == {
    "type": "object",
    "required": ["port"],
    "properties": {"port": {"type": "integer", "default": 8080}, "tier": {"type": "string", "enum": ["a", "b"]}},
  }
  assert spec["source"]["path"] == "t/skeleton"


@pytest.mark.parametrize("change,field,reason", [
  ({"steps": []}, "spec.steps", "no fetch:template step: nothing to render"),
  ({"type": "cli"}, "spec.type", "'cli': use service, website or library"),
  ({"steps": [{"action": "fetch:template", "input": {"url": "https://github.com/x/y"}}]}, "spec.steps", "fetch:template url must be a relative folder, got 'https://github.com/x/y'"),
  ({"steps": [{"action": "fetch:template", "input": {"url": "../../outside"}}]}, "spec.steps", "fetch:template url leaves the repo: '../../outside'"),
])
def test_invalid_backstage_templates(change, field, reason):
  with pytest.raises(Invalid) as error:
    convert_backstage(backstage(**change), "t/template.yaml", ORIGIN)
  assert (error.value.field, error.value.reason) == (field, reason)


def test_without_origin_names_the_flags():
  with pytest.raises(Invalid) as error:
    convert_backstage(backstage(steps=[{"action": "fetch:template", "input": {"url": "./c"}}]), "t/template.yaml", None)
  assert (error.value.field, error.value.reason) == ("source.repo", "required to import templates: pass --repo and --ref")


def test_the_repo_platform_template():
  document = yaml.safe_load((REPO / "platform/templates/python-service/template.yaml").read_text())
  name, spec, steps = convert_platform(document, "platform/templates/python-service/template.yaml", ORIGIN)
  assert name == "python-service"
  assert spec["source"]["path"] == "platform/templates/python-service/content"
  assert spec["owner"] == "team-platform"
  assert spec["parameters"]["properties"]["port"]["default"] == 8000
  assert steps == []
  assert content_folders(document, "platform/templates/python-service/template.yaml") == ["platform/templates/python-service/content"]


def test_flatten_nested_spec():
  assert flatten({"source": {"ref": "v1", "repo": "r"}, "type": "service"}) == {"source.ref": "v1", "source.repo": "r", "type": "service"}
