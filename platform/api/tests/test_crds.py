"""The CRDs and the API agree on group, kinds and required fields."""
from pathlib import Path

import pytest
import yaml

from fakes import FakeState
from platform_api.state import CATALOG_GROUP, CATALOG_PLURALS, GROUP, group_of

CRDS = Path(__file__).parents[3] / "platform" / "crds"


def load(plural: str) -> dict:
  return yaml.safe_load((CRDS / f"catalog-{plural.removesuffix('s')}.yaml").read_text())


@pytest.mark.parametrize("plural,required", [
  ("domains", ["owner"]),
  ("systems", ["owner", "domain"]),
  ("resources", ["owner", "type", "system"]),
  ("templates", ["owner", "type", "source"]),
])
def test_catalog_crd(plural, required):
  crd = load(plural)
  assert crd["metadata"]["name"] == f"{plural}.{CATALOG_GROUP}"
  assert crd["spec"]["group"] == CATALOG_GROUP
  assert crd["spec"]["names"]["plural"] == plural
  spec = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["spec"]
  assert sorted(spec["required"]) == sorted(required)


def test_template_crd_matches_the_api():
  from platform_api.templates import TYPES

  version = load("templates")["spec"]["versions"][0]
  spec = version["schema"]["openAPIV3Schema"]["properties"]["spec"]["properties"]
  assert tuple(spec["type"]["enum"]) == TYPES
  assert sorted(spec["source"]["required"]) == ["path", "ref", "repo"]
  # The CLI fetches repo and ref with git: a CR written straight to the cluster must obey the same rules.
  from platform_api.templates import REF, REPO_URL

  assert spec["source"]["properties"]["repo"]["pattern"] == REPO_URL.pattern
  assert spec["source"]["properties"]["ref"]["pattern"] == REF.pattern
  assert [column["name"] for column in version["additionalPrinterColumns"]] == ["Type", "Default", "Ref"]


def test_group_of():
  assert group_of("environments") == GROUP
  assert all(group_of(plural) == CATALOG_GROUP for plural in CATALOG_PLURALS)


def test_stores_are_per_plural():
  state = FakeState()
  state.create("domains", {"metadata": {"name": "greeter"}, "spec": {}})
  state.create("systems", {"metadata": {"name": "greeter"}, "spec": {}})
  assert state.get("domains", "greeter")["metadata"]["uid"] != state.get("systems", "greeter")["metadata"]["uid"]
  assert state.list("environments") == []


def test_api_role_can_update_catalog():
  deploy = Path(__file__).parents[1] / "deploy" / "platform-api.yaml"
  role = next(doc for doc in yaml.safe_load_all(deploy.read_text()) if doc and doc["kind"] == "Role")
  rule = next(rule for rule in role["rules"] if CATALOG_GROUP in rule["apiGroups"])
  assert {"create", "update", "delete"} <= set(rule["verbs"])
