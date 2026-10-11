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
])
def test_catalog_crd(plural, required):
  crd = load(plural)
  assert crd["metadata"]["name"] == f"{plural}.{CATALOG_GROUP}"
  assert crd["spec"]["group"] == CATALOG_GROUP
  assert crd["spec"]["names"]["plural"] == plural
  spec = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["spec"]
  assert sorted(spec["required"]) == sorted(required)


def test_group_of():
  assert group_of("environments") == GROUP
  assert all(group_of(plural) == CATALOG_GROUP for plural in CATALOG_PLURALS)


def test_stores_are_per_plural():
  state = FakeState()
  state.create("domains", {"metadata": {"name": "greeter"}, "spec": {}})
  state.create("systems", {"metadata": {"name": "greeter"}, "spec": {}})
  assert state.get("domains", "greeter")["metadata"]["uid"] != state.get("systems", "greeter")["metadata"]["uid"]
  assert state.list("environments") == []
