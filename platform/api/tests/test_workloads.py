"""workload deploy|list|get|history (#292): the API writes revisions, the provider keeps the instances."""
import json

import pytest
from fastapi.testclient import TestClient

from fakes import CATALOG_TEAMS, FakeState, FakeTeams
from platform_api.app import create_app
from platform_api.journal import Journal
from test_builds import bearer
from test_workload_specs import indexed
from tokens import TokenFactory


def environment(name, owner="user-1", shared_with=()):
  obj = {
    "metadata": {"name": name, "annotations": {"platform.wasp.silvios.me/owner": owner}},
    "spec": {"profile": "ephemeral"},
  }
  if shared_with:
    obj["spec"]["sharedWith"] = list(shared_with)
  return obj


def close(state, name, status, reason):
  obj = state.stores["workloadrevisions"][name]
  obj["status"] = {"conditions": [{"type": "Ready", "status": status, "reason": reason, "message": reason}]}


@pytest.fixture
def state():
  state = FakeState()
  state.create("environments", environment("demo", shared_with=("team-beta",)))
  state.create("environments", environment("private", owner="someone-else"))
  state.create("components", {"metadata": {"name": "greeting-api"}, "spec": {"owner": "team-alpha", "system": "greeter"}})
  state.create("versions", indexed("greeting-api", "1.0.0", "2026-10-01T10:00:00Z", branch="main"))
  state.create("versions", indexed("greeting-api", "1.1.0-greetings.1", "2026-10-02T10:00:00Z"))
  state.create("versions", indexed("greeting-api", "1.1.0-greetings.2", "2026-10-03T10:00:00Z"))
  state.create("versions", indexed("greeting-api", "0.9.0", "2026-09-01T10:00:00Z", branch="old", app_spec=False))
  return state


@pytest.fixture
def journal_path(tmp_path):
  return tmp_path / "journal.jsonl"


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def client(state, journal_path, tokens):
  return TestClient(create_app(state, Journal(journal_path), tokens.verifier(), teams=FakeTeams(*CATALOG_TEAMS)))


@pytest.fixture
def owner(tokens):
  # Owns the environment demo and is in team-alpha, the owner team of greeting-api.
  return bearer(tokens)


@pytest.fixture
def teammate(tokens):
  # Uses demo through team-beta, but is not in the owner team of greeting-api.
  return bearer(tokens, sub="user-2", teams=("team-beta",))


@pytest.fixture
def admin(tokens):
  return bearer(tokens, sub="admin-1", groups=("platform-users", "platform-admins"), teams=())


DEPLOY = "/v1/environments/demo/workloads/greeting-api/revisions"


def test_deploy_writes_revision_one(client, state, owner, journal_path):
  response = client.post(DEPLOY, json={"version": "1.0.0", "replicas": 2}, headers=owner)
  assert response.status_code == 202, response.text
  body = response.json()
  assert body["name"] == "demo.greeting-api.1"
  assert (body["revision"], body["action"], body["version"], body["replicas"], body["status"], body["open"]) == (1, "deploy", "1.0.0", 2, "Pending", True)
  obj = state.get("workloadrevisions", "demo.greeting-api.1")
  assert obj["spec"]["image"] == "ghcr.io/wasp-foundry/greeting-api"
  assert obj["spec"]["digest"] == "sha256:" + "b" * 64
  assert obj["metadata"]["labels"] == {
    "platform.wasp.silvios.me/environment": "demo",
    "platform.wasp.silvios.me/component": "greeting-api",
    "platform.wasp.silvios.me/instance": "greeting-api",
  }
  assert obj["metadata"]["ownerReferences"][0]["kind"] == "Environment"
  assert obj["metadata"]["ownerReferences"][0]["uid"] == state.get("environments", "demo")["metadata"]["uid"]
  record, applied = [json.loads(line) for line in journal_path.read_text().splitlines()]
  assert (record["kind"], record["name"], applied["id"], applied["applied"]) == ("WorkloadRevision", "demo.greeting-api.1", record["id"], True)


def test_next_deploy_is_the_newest_plus_one(client, state, owner):
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  body = client.post(DEPLOY, json={"branch": "feat/greetings"}, headers=owner).json()
  # The branch is pinned to its newest version.
  assert (body["name"], body["version"]) == ("demo.greeting-api.2", "1.1.0-greetings.2")


def test_concurrent_deploy_is_a_conflict(client, state, owner, monkeypatch):
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  # The other request created revision 1 after this one listed the revisions.
  listed = state.list
  monkeypatch.setattr(state, "list", lambda plural: [] if plural == "workloadrevisions" else listed(plural))
  response = client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  assert response.status_code == 409
  assert "taken by a concurrent request" in response.json()["error"]["message"]


@pytest.mark.parametrize("body,status,message", [
  ({"version": "2.0.0"}, 404, "no version 2.0.0 in the index"),
  ({"branch": "main-2"}, 404, "no version built from branch 'main-2'"),
  ({"version": "0.9.0"}, 409, "SpecNotIndexed"),
  ({}, 422, "either version or branch"),
  ({"version": "1.0.0", "branch": "main"}, 422, "either version or branch"),
  ({"version": "latest"}, 422, "major"),
  ({"version": "1.0.0", "replicas": 50}, 422, "replicas"),
])
def test_deploy_refusals(client, owner, body, status, message):
  response = client.post(DEPLOY, json=body, headers=owner)
  assert response.status_code == status, response.text
  assert message in response.json()["error"]["message"]


def test_deploy_needs_the_owner_team(client, teammate):
  response = client.post(DEPLOY, json={"version": "1.0.0"}, headers=teammate)
  assert response.status_code == 403
  assert "owner team (team-alpha)" in response.json()["error"]["message"]


def test_deploy_needs_can_use(client, owner):
  response = client.post("/v1/environments/private/workloads/greeting-api/revisions", json={"version": "1.0.0"}, headers=owner)
  assert response.status_code == 403


def test_admin_deploys_anywhere(client, admin):
  response = client.post("/v1/environments/private/workloads/greeting-api/revisions", json={"version": "1.0.0"}, headers=admin)
  assert response.status_code == 202


def test_deploy_unknown_environment_or_component(client, owner):
  assert client.post("/v1/environments/nope/workloads/greeting-api/revisions", json={"version": "1.0.0"}, headers=owner).status_code == 404
  response = client.post("/v1/environments/demo/workloads/other-api/revisions", json={"version": "1.0.0"}, headers=owner)
  assert response.status_code == 404
  assert "component 'other-api' not found" in response.json()["error"]["message"]


def test_list_shows_a_pending_first_deploy(client, owner, teammate):
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  # Reading needs can_use only.
  items = client.get("/v1/environments/demo/workloads", headers=teammate).json()["items"]
  assert [(item["name"], item["status"], item["version"], item["latestRevision"]["revision"]) for item in items] == [("greeting-api@demo", "Pending", None, 1)]


def test_list_hides_a_failed_first_deploy(client, state, owner):
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  close(state, "demo.greeting-api.1", "False", "ResourcesNotSupported")
  assert client.get("/v1/environments/demo/workloads", headers=owner).json()["items"] == []
  assert client.get("/v1/environments/demo/workloads/greeting-api", headers=owner).status_code == 404


def test_get_shows_the_instance_the_provider_keeps(client, state, owner):
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  close(state, "demo.greeting-api.1", "True", "Succeeded")
  state.create("workloadinstances", {
    "metadata": {"name": "demo.greeting-api"},
    "spec": {"environment": "demo", "instance": "greeting-api", "component": "greeting-api"},
    "status": {
      "revision": 1, "version": "1.0.0", "image": "ghcr.io/wasp-foundry/greeting-api@sha256:" + "b" * 64,
      "replicas": {"desired": 1, "ready": 1}, "url": "http://greeting-api.apps:80",
      "conditions": [{"type": "Ready", "status": "True", "reason": "Available"}],
    },
  })
  body = client.get("/v1/environments/demo/workloads/greeting-api", headers=owner).json()
  assert (body["status"], body["version"], body["revision"], body["url"]) == ("Available", "1.0.0", 1, "http://greeting-api.apps:80")
  assert body["replicas"] == {"desired": 1, "ready": 1}
  assert body["latestRevision"]["status"] == "Succeeded"


def test_history_lists_revisions_in_order(client, state, owner, teammate):
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  close(state, "demo.greeting-api.1", "True", "Succeeded")
  client.post(DEPLOY, json={"version": "1.1.0-greetings.1"}, headers=owner)
  items = client.get("/v1/environments/demo/revisions", params={"instance": "greeting-api"}, headers=teammate).json()["items"]
  assert [(item["revision"], item["version"], item["status"], item["requestedBy"]) for item in items] == [
    (1, "1.0.0", "Succeeded", "dev@example.com"), (2, "1.1.0-greetings.1", "Pending", "dev@example.com"),
  ]


def test_reads_need_can_use(client, owner):
  assert client.get("/v1/environments/private/workloads", headers=owner).status_code == 403
  assert client.get("/v1/environments/private/revisions", headers=owner).status_code == 403


def instance(state, environment="demo", revision=1, version="1.0.0"):
  state.create("workloadinstances", {
    "metadata": {"name": f"{environment}.greeting-api"},
    "spec": {"environment": environment, "instance": "greeting-api", "component": "greeting-api"},
    "status": {"revision": revision, "version": version, "conditions": [{"type": "Ready", "status": "True", "reason": "Available"}]},
  })


def test_rollback_copies_version_and_overrides(client, state, owner):
  client.post(DEPLOY, json={"version": "1.0.0", "replicas": 3}, headers=owner)
  close(state, "demo.greeting-api.1", "True", "Succeeded")
  client.post(DEPLOY, json={"version": "1.1.0-greetings.1"}, headers=owner)
  close(state, "demo.greeting-api.2", "True", "Succeeded")
  response = client.post(DEPLOY, json={"rollbackTo": 1}, headers=owner)
  assert response.status_code == 202, response.text
  body = response.json()
  assert (body["name"], body["action"], body["rollbackOf"], body["version"], body["replicas"]) == ("demo.greeting-api.3", "rollback", 1, "1.0.0", 3)
  spec = state.get("workloadrevisions", "demo.greeting-api.3")["spec"]
  assert spec["digest"] == "sha256:" + "b" * 64


@pytest.mark.parametrize("setup,body,status,message", [
  (None, {"rollbackTo": 7}, 404, "revision 7 not found"),
  ("ResourcesNotSupported", {"rollbackTo": 1}, 409, "revision 1 did not succeed (ResourcesNotSupported)"),
  ("Succeeded", {"rollbackTo": 1, "version": "1.0.0"}, 422, "give nothing else"),
  ("Succeeded", {"rollbackTo": 0}, 422, "rollbackTo"),
])
def test_rollback_refusals(client, state, owner, setup, body, status, message):
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  if setup:
    close(state, "demo.greeting-api.1", "True" if setup == "Succeeded" else "False", setup)
  response = client.post(DEPLOY, json=body, headers=owner)
  assert response.status_code == status, response.text
  assert message in response.json()["error"]["message"]


def test_rollback_needs_the_owner_team(client, state, owner, teammate):
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  close(state, "demo.greeting-api.1", "True", "Succeeded")
  response = client.post(DEPLOY, json={"rollbackTo": 1}, headers=teammate)
  assert response.status_code == 403
  assert "rollback of 'greeting-api'" in response.json()["error"]["message"]


def test_rollback_to_a_remove_is_refused(client, state, owner):
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  close(state, "demo.greeting-api.1", "True", "Succeeded")
  instance(state)
  client.delete("/v1/environments/demo/workloads/greeting-api", headers=owner)
  close(state, "demo.greeting-api.2", "True", "Succeeded")
  response = client.post(DEPLOY, json={"rollbackTo": 2}, headers=owner)
  assert response.status_code == 409
  assert "is a remove" in response.json()["error"]["message"]


def test_remove_writes_a_remove_revision(client, state, owner):
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  close(state, "demo.greeting-api.1", "True", "Succeeded")
  instance(state)
  response = client.delete("/v1/environments/demo/workloads/greeting-api", headers=owner)
  assert response.status_code == 202, response.text
  body = response.json()
  assert (body["name"], body["action"], body["version"]) == ("demo.greeting-api.2", "remove", None)
  # Done by the provider: the instance goes, the history stays.
  close(state, "demo.greeting-api.2", "True", "Succeeded")
  del state.stores["workloadinstances"]["demo.greeting-api"]
  assert client.get("/v1/environments/demo/workloads", headers=owner).json()["items"] == []
  assert len(client.get("/v1/environments/demo/revisions", headers=owner).json()["items"]) == 2


def test_remove_refusals(client, state, owner, teammate):
  assert client.delete("/v1/environments/demo/workloads/greeting-api", headers=owner).status_code == 404
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  assert client.delete("/v1/environments/demo/workloads/greeting-api", headers=teammate).status_code == 403


def test_component_get_shows_where_it_runs(client, state, owner, teammate, tokens):
  instance(state, "demo")
  instance(state, "private", revision=4, version="1.1.0-greetings.2")
  body = client.get("/v1/catalog/components/greeting-api", headers=owner).json()
  # private belongs to someone else: the owner of demo does not see it.
  assert body["runningIn"] == [{"environment": "demo", "instance": "greeting-api", "version": "1.0.0", "revision": 1, "status": "Available"}]
  admin = bearer(tokens, sub="admin-1", groups=("platform-users", "platform-admins"), teams=())
  assert [item["environment"] for item in client.get("/v1/catalog/components/greeting-api", headers=admin).json()["runningIn"]] == ["demo", "private"]
