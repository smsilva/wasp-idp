"""Templates through the import plan (#190 + ADR 0024): `catalog import` and `templates:import`."""
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from fakes import CATALOG_TEAMS, FakeState, FakeTeams
from platform_api.app import create_app
from platform_api.journal import Journal
from tokens import TokenFactory

REPO = Path(__file__).parents[3]
ORIGIN = {"repo": "https://github.com/smsilva/wasp-idp", "ref": "main"}
CATALOG_ROUTE = "/v1/catalog/import"
ROUTE = "/v1/catalog/templates:import"


@pytest.fixture
def state():
  return FakeState()


@pytest.fixture
def client(state, tmp_path):
  tokens = TokenFactory()
  client = TestClient(create_app(state, Journal(tmp_path / "journal.jsonl"), tokens.verifier(), teams=FakeTeams(*CATALOG_TEAMS)))
  client.admin = {"Authorization": f"Bearer {tokens.issue(sub='admin-1', groups=['platform-admins'])}"}
  client.user = {"Authorization": f"Bearer {tokens.issue()}"}
  return client


def read(folder: str) -> list[dict]:
  """What the CLI sends: every YAML document, with its path relative to the repo root."""
  documents = []
  for file in sorted((REPO / folder).rglob("*")):
    if file.is_file() and file.suffix in (".yaml", ".yml"):
      path = file.relative_to(REPO).as_posix()
      loaded = [document for document in yaml.safe_load_all(file.read_text()) if document is not None]
      documents += [{"source": f"{path}#{index}", "path": path, "document": document} for index, document in enumerate(loaded, 1)]
  return documents


def plan(client, documents, route=ROUTE, headers=None, origin=ORIGIN, **extra):
  body = {"documents": documents, **({"source": origin} if origin else {}), **extra}
  return client.post(route, json=body, headers=headers or client.admin)


def rows(result: dict) -> list[tuple]:
  return [(item["kind"], item["name"], item["action"], item.get("reason")) for item in result["items"]]


GUESTS = [{"source": "org.yaml#1", "path": "org.yaml", "document": {"apiVersion": "backstage.io/v1alpha1", "kind": "Group", "metadata": {"name": "guests"}, "spec": {"type": "team"}}}]


def test_owner_of_the_backstage_template_must_be_a_team(client):
  result = plan(client, read("idp/templates/python-service")).json()
  item = next(item for item in result["items"] if item["kind"] == "Template")
  assert (item["action"], item["field"]) == ("error", "spec.owner")
  assert item["reason"].startswith("team 'guests' not found")


def test_backstage_template_plan_lists_the_ignored_steps(client):
  # Its owner is group:default/guests: through catalog import, the Group comes along as a team (ADR 0026).
  result = plan(client, GUESTS + read("idp/templates/python-service"), route=CATALOG_ROUTE).json()
  assert ("Template", "python-service", "create", None) in rows(result)
  steps = [row for row in rows(result) if row[0] == "Step"]
  assert ("Step", "python-service/publish", "skip", "publish:github: the platform creates the repo") in steps
  assert ("Step", "python-service/gitops-pr", "skip", "publish:github:pull-request: GitOps belongs to the release") in steps
  # The content of a template is not catalog data: catalog-info.yaml there is not a real Component.
  owned = [item for item in result["items"] if item.get("reason") == "part of template python-service"]
  assert "Component" in {item["kind"] for item in owned}
  assert {item["source"].split("#")[0].split("/")[3] for item in owned} == {"content", "gitops"}
  assert result["summary"]["error"] == 0


def test_apply_creates_the_template(client, state):
  result = plan(client, GUESTS + read("idp/templates/python-service"), route=CATALOG_ROUTE, dryRun=False)
  assert result.status_code == 200, result.text
  spec = state.stores["templates"]["python-service"]["spec"]
  assert spec["source"] == {"repo": ORIGIN["repo"], "path": "idp/templates/python-service/content", "ref": "main"}
  assert spec["copyWithoutRendering"] == [".github/workflows/*"]
  again = plan(client, read("idp/templates/python-service")).json()
  assert ("Template", "python-service", "unchanged", None) in rows(again)


def test_update_shows_flat_changes_and_keeps_the_default(client, state):
  plan(client, read("platform/templates"), dryRun=False)
  client.post("/v1/catalog/templates/python-service/default", headers=client.admin)
  result = plan(client, read("platform/templates"), origin={**ORIGIN, "ref": "v2"}).json()
  item = next(item for item in result["items"] if item["kind"] == "Template")
  assert (item["action"], item["changes"]) == ("update", {"source.ref": ["main", "v2"]})
  plan(client, read("platform/templates"), origin={**ORIGIN, "ref": "v2"}, dryRun=False)
  assert state.stores["templates"]["python-service"]["spec"]["default"] is True


def test_without_origin_the_template_is_an_error_and_the_rest_goes_on(client):
  documents = read("platform/templates") + read("idp/catalog")
  result = plan(client, documents, route=CATALOG_ROUTE, origin=None).json()
  template = next(item for item in result["items"] if item["kind"] == "Template")
  assert (template["action"], template["field"]) == ("error", "source.repo")
  assert template["reason"] == "required to import templates: pass --repo and --ref"
  assert result["summary"]["create"] == 18


def test_catalog_import_takes_templates_too(client, state):
  result = plan(client, read("idp/catalog") + read("platform/templates"), route=CATALOG_ROUTE, dryRun=False)
  assert result.status_code == 200, result.text
  assert "python-service" in state.stores["templates"]
  assert "platform" in state.stores["domains"]


def test_templates_route_skips_other_kinds(client):
  result = plan(client, read("idp/catalog")).json()
  assert result["summary"]["create"] == 0
  assert ("Domain", "platform", "skip", "not a template: use 'platform catalog import'") in rows(result)


def test_user_is_forbidden(client):
  result = plan(client, read("platform/templates"), headers=client.user).json()
  item = next(item for item in result["items"] if item["kind"] == "Template")
  assert item["action"] == "forbidden"
  assert item["reason"] == "creating a template requires group 'platform-admins'"


@pytest.mark.parametrize("origin,field", [
  ({"repo": "file:///etc", "ref": "main"}, "source.repo"),
  ({"repo": ORIGIN["repo"], "ref": "a b"}, "source.ref"),
])
def test_invalid_origin_is_422(client, origin, field):
  response = plan(client, read("platform/templates"), origin=origin)
  assert response.status_code == 422
  assert response.json()["error"]["message"].startswith(field)


def test_template_content_is_skipped_even_when_the_template_has_errors(client):
  result = plan(client, read("idp/templates/python-service"), route=CATALOG_ROUTE, origin=None).json()
  components = [item for item in result["items"] if item["kind"] == "Component"]
  assert [item["reason"] for item in components] == ["part of template python-service"]


def test_changing_the_type_on_import_drops_the_default(client, state):
  plan(client, read("platform/templates"), dryRun=False)
  client.post("/v1/catalog/templates/python-service/default", headers=client.admin)
  documents = [document for document in read("platform/templates") if document["path"].endswith("template.yaml")]
  documents[0]["document"] = {**documents[0]["document"], "type": "website"}
  result = plan(client, documents, dryRun=False)
  assert result.status_code == 200, result.text
  spec = state.stores["templates"]["python-service"]["spec"]
  assert spec["type"] == "website" and "default" not in spec


@pytest.mark.parametrize("change,field", [
  ({"steps": [{"action": "fetch:template", "input": "oops"}]}, "spec.steps"),
  ({"steps": "oops"}, "spec.steps"),
  ({"parameters": [{"properties": [1]}], "steps": [{"action": "fetch:template", "input": {"url": "./c"}}]}, "spec.parameters"),
])
def test_malformed_backstage_template_is_an_error_item(client, change, field):
  document = {
    "apiVersion": "scaffolder.backstage.io/v1beta3", "kind": "Template", "metadata": {"name": "bad"},
    "spec": {"owner": "team-a", "type": "service", **change},
  }
  response = plan(client, [{"source": "t/template.yaml#1", "path": "t/template.yaml", "document": document}])
  assert response.status_code == 200, response.text
  item = response.json()["items"][0]
  assert (item["action"], item["field"]) == ("error", field)


def test_template_with_non_mapping_metadata_is_an_error_item(client):
  document = {"apiVersion": "scaffolder.backstage.io/v1beta3", "kind": "Template", "metadata": "x", "spec": {}}
  response = plan(client, [{"source": "t/template.yaml#1", "path": "t/template.yaml", "document": document}])
  assert response.status_code == 200, response.text
  assert response.json()["items"][0]["action"] == "error"
