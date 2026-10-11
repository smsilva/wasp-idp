from pathlib import Path

import pytest

from wasp_score import APP_SPEC, RESOURCE_TYPES, check

SEED = (Path(__file__).parents[4] / "platform" / "templates" / "python-service" / "content" / "app-spec.yaml").read_text()
# The seed renders ${{ values.* }}; a rendered app-spec.yaml carries the values.
SPEC = SEED.replace("${{ values.name }}", "greeting-api").replace("${{ values.port }}", "8000")


def nothing(name: str) -> bool:
  return False


def test_the_seed_is_valid():
  result = check(SPEC, nothing)
  assert result.valid
  assert result.document["metadata"]["name"] == "greeting-api"
  assert [item["type"] for item in result.resources] == ["postgres", "dns", "route"]


def test_unknown_type_and_missing_id():
  spec = SPEC.replace("type: postgres", "type: redis\n  cache:\n    type: postgres\n    id: shared-cache")
  result = check(spec, nothing)
  assert {item["field"] for item in result.errors} == {"resources.db.type", "resources.cache.id"}


def test_a_known_id_passes():
  spec = SPEC.replace("type: postgres", "type: postgres\n    id: shared-db")
  assert check(spec, lambda name: name == "shared-db").valid


def test_the_resource_types_can_be_narrowed():
  result = check(SPEC, nothing, resource_types=("postgres",))
  assert [item["field"] for item in result.errors] == ["resources.dns.type", "resources.route.type"]
  assert RESOURCE_TYPES == ("postgres", "dns", "route")


def test_the_score_schema_is_checked():
  result = check(SPEC.replace("apiVersion: score.dev/v1b1", "apiVersion: platform/v1"), nothing)
  assert [item["field"] for item in result.errors] == ["apiVersion"]


@pytest.mark.parametrize("text", ["a: [b", "- not a mapping", ""])
def test_not_a_score(text):
  result = check(text, nothing)
  assert not result.valid
  assert result.errors[0]["field"] in (APP_SPEC, "(root)")


def test_a_document_that_json_cannot_hold():
  spec = SPEC.replace("metadata:", "metadata:\n  released: 2026-10-11", 1)
  result = check(spec, nothing)
  assert not result.valid
