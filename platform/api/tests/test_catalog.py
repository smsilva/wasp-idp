import json

import pytest
from fastapi.testclient import TestClient

from fakes import CATALOG_TEAMS, FakeState, FakeTeams
from platform_api.app import create_app
from platform_api.catalog import CREATED_BY_ANNOTATION
from platform_api.journal import Journal
from tokens import TokenFactory


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


@pytest.fixture
def other(tokens):
  return bearer(tokens, sub="user-2", email="other@example.com")


@pytest.fixture
def tree(client, admin, user):
  """communication > messaging > greeter > greeting-db, the example catalog of the repo."""
  for path, body, headers in [
    ("domains", {"name": "communication", "owner": "team-alpha"}, admin),
    ("domains", {"name": "messaging", "owner": "team-alpha", "parent": "communication"}, admin),
    ("systems", {"name": "greeter", "owner": "team-alpha", "domain": "messaging"}, user),
    ("resources", {"name": "greeting-db", "owner": "team-alpha", "type": "database", "system": "greeter"}, user),
  ]:
    response = client.post(f"/v1/catalog/{path}", json=body, headers=headers)
    assert response.status_code == 201, response.text


def journal(journal_path):
  if not journal_path.exists():
    return []
  return [json.loads(line) for line in journal_path.read_text().splitlines() if "action" in line]


def test_admin_creates_domain_and_subdomain(client, admin):
  client.post("/v1/catalog/domains", json={"name": "communication", "owner": "team-alpha"}, headers=admin)
  response = client.post("/v1/catalog/domains", json={"name": "messaging", "owner": "team-alpha", "parent": "communication"}, headers=admin)
  assert response.status_code == 201
  body = response.json()
  assert (body["kind"], body["name"], body["parent"], body["owner"]) == ("Domain", "messaging", "communication", "team-alpha")


def test_user_cannot_create_domain(client, user):
  response = client.post("/v1/catalog/domains", json={"name": "communication", "owner": "team-alpha"}, headers=user)
  assert response.status_code == 403
  assert response.json()["error"]["code"] == "forbidden"


def test_user_creates_system_and_resource_with_creator(client, state, tree):
  assert state.stores["systems"]["greeter"]["metadata"]["annotations"][CREATED_BY_ANNOTATION] == "user-1"
  assert state.stores["resources"]["greeting-db"]["spec"] == {"owner": "team-alpha", "type": "database", "system": "greeter"}


def test_missing_parent_is_422_and_not_journaled(client, user, journal_path):
  response = client.post("/v1/catalog/systems", json={"name": "greeter", "owner": "team-alpha", "domain": "nope"}, headers=user)
  assert response.status_code == 422
  assert response.json()["error"]["message"] == "system 'greeter': domain 'nope' not found"
  assert journal(journal_path) == []


@pytest.mark.parametrize("path,body,message", [
  ("domains", {"name": "x", "owner": "team-alpha", "type": "database"}, "type: not a field of domain"),
  ("systems", {"name": "x", "owner": "team-alpha"}, "domain: required for system"),
])
def test_fields_per_kind_are_422(client, admin, path, body, message):
  response = client.post(f"/v1/catalog/{path}", json=body, headers=admin)
  assert response.status_code == 422
  assert response.json()["error"]["message"] == message


def test_invalid_name_is_422(client, admin):
  response = client.post("/v1/catalog/domains", json={"name": "Communication", "owner": "team-alpha"}, headers=admin)
  assert response.status_code == 422
  assert response.json()["error"]["code"] == "invalid_request"


def test_duplicate_is_409(client, admin, tree):
  response = client.post("/v1/catalog/domains", json={"name": "communication", "owner": "team-alpha"}, headers=admin)
  assert response.status_code == 409
  assert response.json()["error"]["message"] == "domain 'communication' already exists"


def test_same_name_in_two_kinds(client, admin):
  client.post("/v1/catalog/domains", json={"name": "greeter", "owner": "team-alpha"}, headers=admin)
  response = client.post("/v1/catalog/systems", json={"name": "greeter", "owner": "team-alpha", "domain": "greeter"}, headers=admin)
  assert response.status_code == 201


def test_unknown_kind_is_404(client, admin):
  response = client.get("/v1/catalog/components", headers=admin)
  assert response.status_code == 404
  assert "unknown catalog kind 'components'" in response.json()["error"]["message"]


def test_list_kind_sorted(client, admin, user, tree):
  client.post("/v1/catalog/systems", json={"name": "notifier", "owner": "team-beta", "domain": "communication"}, headers=user)
  items = client.get("/v1/catalog/systems", headers=user).json()["items"]
  assert [(item["name"], item["domain"]) for item in items] == [("greeter", "messaging"), ("notifier", "communication")]


def test_get_shows_dependents(client, user, tree):
  body = client.get("/v1/catalog/domains/communication", headers=user).json()
  assert body["dependents"] == ["domain/messaging"]
  assert client.get("/v1/catalog/systems/greeter", headers=user).json()["dependents"] == ["resource/greeting-db"]
  assert client.get("/v1/catalog/systems/nope", headers=user).status_code == 404


def test_delete_with_dependents_is_409(client, admin, tree):
  response = client.delete("/v1/catalog/systems/greeter", headers=admin)
  assert response.status_code == 409
  assert response.json()["error"]["message"] == "system 'greeter' has dependents: resource/greeting-db"


def test_delete_leaf_then_parent(client, admin, tree):
  for path in ["resources/greeting-db", "systems/greeter", "domains/messaging", "domains/communication"]:
    response = client.delete(f"/v1/catalog/{path}", headers=admin)
    assert response.status_code == 204, f"{path}: {response.text}"
    assert response.content == b""
  assert client.get("/v1/catalog/entities", headers=admin).json()["items"] == []


def test_delete_authorization(client, user, other, admin, tree):
  assert client.delete("/v1/catalog/resources/greeting-db", headers=other).status_code == 403
  assert client.delete("/v1/catalog/resources/greeting-db", headers=user).status_code == 204
  # The admin check comes before the dependents check: a non-admin learns nothing about the tree.
  response = client.delete("/v1/catalog/domains/messaging", headers=user)
  assert response.status_code == 403
  assert response.json()["error"]["message"] == "deleting a domain requires group 'platform-admins'"


def test_journal_records_accepted_requests_only(client, other, admin, tree, journal_path):
  client.delete("/v1/catalog/resources/greeting-db", headers=other)
  client.delete("/v1/catalog/resources/greeting-db", headers=admin)
  entries = journal(journal_path)
  assert [(entry["action"], entry["kind"], entry["name"]) for entry in entries] == [
    ("create", "Domain", "communication"),
    ("create", "Domain", "messaging"),
    ("create", "System", "greeter"),
    ("create", "Resource", "greeting-db"),
    ("delete", "Resource", "greeting-db"),
  ]
  assert entries[2]["actor"] == "user-1 (dev@example.com)"


def test_entities_filters(client, user, tree):
  items = client.get("/v1/catalog/entities", headers=user).json()["items"]
  assert [(item["kind"], item["name"], item["parent"]) for item in items] == [
    ("Domain", "communication", None),
    ("Domain", "messaging", "communication"),
    ("System", "greeter", "messaging"),
    ("Resource", "greeting-db", "greeter"),
  ]
  systems = client.get("/v1/catalog/entities", params={"kind": "system"}, headers=user).json()["items"]
  assert [item["name"] for item in systems] == ["greeter"]
  assert client.get("/v1/catalog/entities", params={"owner": "team-beta"}, headers=user).json()["items"] == []
  assert client.get("/v1/catalog/entities", params={"kind": "component"}, headers=user).status_code == 422


def test_long_description_is_422(client, admin):
  response = client.post("/v1/catalog/domains", json={"name": "communication", "owner": "team-alpha", "description": "x" * 1001}, headers=admin)
  assert response.status_code == 422
  assert "description" in response.json()["error"]["message"]


def test_owner_must_be_an_existing_team(client, admin):
  response = client.post("/v1/catalog/domains", json={"name": "lonely", "owner": "team-nobody"}, headers=admin)
  assert response.status_code == 422
  assert "team 'team-nobody' not found" in response.json()["error"]["message"]


def test_catalog_writes_need_teams(state, journal_path, tokens, admin):
  client = TestClient(create_app(state, Journal(journal_path), tokens.verifier()))
  assert client.post("/v1/catalog/domains", json={"name": "d", "owner": "team-alpha"}, headers=admin).status_code == 503
