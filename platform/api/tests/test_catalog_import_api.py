import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from fakes import CATALOG_TEAMS, FakeState, FakeTeams
from platform_api.app import create_app
from platform_api.catalog import CREATED_BY_ANNOTATION
from platform_api.journal import Journal
from tokens import TokenFactory

CATALOG = Path(__file__).parents[3] / "idp" / "catalog"
ROUTE = "/v1/catalog/import"


@pytest.fixture
def state():
  return FakeState()


@pytest.fixture
def journal_path(tmp_path):
  return tmp_path / "journal.jsonl"


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def client(state, journal_path, tokens):
  return TestClient(create_app(state, Journal(journal_path), tokens.verifier(), teams=FakeTeams(*CATALOG_TEAMS)))


def bearer(tokens, **claims):
  return {"Authorization": f"Bearer {tokens.issue(**claims)}"}


@pytest.fixture
def admin(tokens):
  return bearer(tokens, sub="admin-1", groups=["platform-admins"])


@pytest.fixture
def user(tokens):
  return bearer(tokens)


def doc(kind, name, spec):
  return {"apiVersion": "backstage.io/v1alpha1", "kind": kind, "metadata": {"name": name}, "spec": spec}


def sourced(*documents):
  return [{"source": f"t.yaml#{index}", "document": document} for index, document in enumerate(documents, 1)]


TREE = sourced(
  doc("Domain", "communication", {"owner": "group:default/team-alpha"}),
  doc("Domain", "messaging", {"owner": "group:default/team-alpha", "subdomainOf": "communication"}),
  doc("System", "greeter", {"owner": "group:default/team-alpha", "domain": "messaging"}),
)


def journal(journal_path):
  if not journal_path.exists():
    return []
  return [json.loads(line) for line in journal_path.read_text().splitlines() if "action" in line]


def review(client, headers, documents):
  response = client.post(ROUTE, json={"documents": documents}, headers=headers)
  assert response.status_code == 200, response.text
  return response.json()


def test_dry_run_is_the_default_and_writes_nothing(client, admin, state, journal_path):
  plan = review(client, admin, TREE)
  assert [item["action"] for item in plan["items"]] == ["create"] * 3
  assert plan["applied"] is False
  assert state.list("domains") == [] and journal(journal_path) == []


def test_apply_with_the_reviewed_hash(client, admin, state, journal_path):
  plan = review(client, admin, TREE)
  response = client.post(ROUTE, json={"documents": TREE, "dryRun": False, "planHash": plan["planHash"]}, headers=admin)
  assert response.status_code == 200, response.text
  body = response.json()
  assert body["applied"] is True
  assert all(item["applied"] for item in body["items"])
  assert state.stores["systems"]["greeter"]["metadata"]["annotations"][CREATED_BY_ANNOTATION] == "admin-1"
  assert [(entry["action"], entry["kind"], entry["name"]) for entry in journal(journal_path)] == [
    ("create", "Domain", "communication"), ("create", "Domain", "messaging"), ("create", "System", "greeter"),
  ]


def test_second_import_is_all_unchanged(client, admin):
  client.post(ROUTE, json={"documents": TREE, "dryRun": False}, headers=admin)
  plan = review(client, admin, TREE)
  assert plan["summary"]["unchanged"] == 3 and plan["summary"]["create"] == 0


def test_update_keeps_creator_and_is_journaled(client, admin, user, state, journal_path):
  client.post(ROUTE, json={"documents": TREE, "dryRun": False}, headers=admin)
  changed = sourced(doc("System", "greeter", {"owner": "group:default/team-beta", "domain": "messaging"}))
  response = client.post(ROUTE, json={"documents": changed, "dryRun": False}, headers=admin)
  assert response.status_code == 200, response.text
  system = state.stores["systems"]["greeter"]
  assert system["spec"]["owner"] == "team-beta"
  assert system["metadata"]["annotations"][CREATED_BY_ANNOTATION] == "admin-1"
  assert journal(journal_path)[-1]["action"] == "update"


def test_errors_block_the_apply(client, admin, state, journal_path):
  documents = TREE + sourced(doc("System", "orphan", {"owner": "team-alpha", "domain": "nowhere"}))
  response = client.post(ROUTE, json={"documents": documents, "dryRun": False}, headers=admin)
  assert response.status_code == 422
  error = response.json()["error"]
  assert error["code"] == "invalid_request"
  assert error["plan"]["summary"]["error"] == 1
  assert state.list("domains") == [] and journal(journal_path) == []


def test_forbidden_blocks_the_apply(client, user, state):
  response = client.post(ROUTE, json={"documents": TREE, "dryRun": False}, headers=user)
  assert response.status_code == 422
  assert response.json()["error"]["plan"]["summary"]["forbidden"] == 1
  assert state.list("systems") == []


def test_stale_hash_is_409_and_writes_nothing(client, admin, state):
  plan = review(client, admin, TREE)
  client.post("/v1/catalog/domains", json={"name": "communication", "owner": "team-beta"}, headers=admin)
  response = client.post(ROUTE, json={"documents": TREE, "dryRun": False, "planHash": plan["planHash"]}, headers=admin)
  assert response.status_code == 409
  error = response.json()["error"]
  assert error["message"] == "catalog changed since the plan was made: review the plan again"
  assert error["plan"]["items"][0]["action"] == "update"
  assert state.list("systems") == []


def test_failure_midway_stops_and_reports(client, admin, state):
  def collide(obj):
    if obj["metadata"]["name"] == "communication":
      state.stores["domains"]["messaging"] = {"metadata": {"name": "messaging", "resourceVersion": "99"}, "spec": {}}
  state.on_create = collide
  response = client.post(ROUTE, json={"documents": TREE, "dryRun": False}, headers=admin)
  assert response.status_code == 409
  items = response.json()["error"]["plan"]["items"]
  assert items[0].get("applied") is True
  assert items[1]["failed"] == "created by someone else since the plan was made"
  assert "applied" not in items[2]
  assert "greeter" not in state.stores["systems"]


def test_more_than_500_documents_is_422(client, admin):
  documents = sourced(*[doc("Domain", f"d{index}", {"owner": "team-alpha"}) for index in range(501)])
  assert client.post(ROUTE, json={"documents": documents}, headers=admin).status_code == 422


def test_requires_login(client):
  assert client.post(ROUTE, json={"documents": TREE}).status_code == 401


def load_catalog():
  documents = []
  for path in sorted(CATALOG.rglob("*")):
    if path.suffix in (".yaml", ".yml"):
      loaded = [document for document in yaml.safe_load_all(path.read_text()) if document is not None]
      documents += [{"source": f"{path.relative_to(CATALOG)}#{index}", "document": document} for index, document in enumerate(loaded, 1)]
  return documents


def test_the_repo_catalog_imports_cleanly(client, admin):
  plan = review(client, admin, load_catalog())
  summary = plan["summary"]
  assert (summary["create"], summary["error"], summary["forbidden"]) == (18, 0, 0)
  assert summary["unchanged"] == 3  # the Groups of org.yaml: the fixture's teams already exist
  assert summary["skip"] == 2  # 2 mkdocs.yml
  created = {(item["kind"], item["name"]) for item in plan["items"] if item["action"] == "create"}
  assert {("Domain", "platform"), ("System", "platform"), ("Domain", "messaging"), ("Resource", "greeting-avatars")} <= created
  applied = client.post(ROUTE, json={"documents": load_catalog(), "dryRun": False, "planHash": plan["planHash"]}, headers=admin)
  assert applied.status_code == 200, applied.text
  assert review(client, admin, load_catalog())["summary"]["unchanged"] == 21  # 18 entities and 3 teams


class KubeError(Exception):
  """Shaped like kubernetes.client.ApiException: str() carries headers and body."""
  status, reason = 500, "Internal Server Error"

  def __str__(self):
    return "(500)\nReason: Internal Server Error\nHTTP response headers: {'Audit-Id': 'secret'}\nHTTP response body: {...}"


def test_unexpected_write_error_is_reported_short(client, admin, state):
  def boom(obj):
    raise KubeError()
  state.on_create = boom
  response = client.post(ROUTE, json={"documents": TREE, "dryRun": False}, headers=admin)
  assert response.status_code == 409
  failed = response.json()["error"]["plan"]["items"][0]["failed"]
  assert failed == "kubernetes error 500: Internal Server Error"


def test_the_repo_catalog_creates_its_teams(state, journal_path, tokens, admin):
  teams = FakeTeams()
  client = TestClient(create_app(state, Journal(journal_path), tokens.verifier(), teams=teams))
  plan = review(client, admin, load_catalog())
  assert [(item["kind"], item["action"]) for item in plan["items"][:3]] == [("Group", "create")] * 3
  assert plan["summary"]["create"] == 21
  applied = client.post(ROUTE, json={"documents": load_catalog(), "dryRun": False, "planHash": plan["planHash"]}, headers=admin)
  assert applied.status_code == 200, applied.text
  assert teams.names() == ["team-alpha", "team-beta", "team-platform"]
  assert review(client, admin, load_catalog())["summary"]["unchanged"] == 21


def test_import_needs_teams(state, journal_path, tokens, admin):
  client = TestClient(create_app(state, Journal(journal_path), tokens.verifier()))
  response = client.post(ROUTE, json={"documents": load_catalog()}, headers=admin)
  assert response.status_code == 503
