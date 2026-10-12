"""The binding policy of an environment (#305)."""
import json

import pytest
from fastapi.testclient import TestClient

from platform_api.app import create_app
from platform_api.journal import Journal
from fakes import FakeState, FakeTeams
from tokens import TokenFactory

COMPOSE = {"type": "postgres", "mode": "compose", "params": {"instance": "shared-pg"}}
BIND = {"type": "postgres", "class": "restored", "mode": "bind", "params": {"secretRef": "restored-db", "host": "shared-pg.resources", "port": "5432", "database": "restored", "username": "restored"}}


@pytest.fixture
def state():
  state = FakeState()
  state.create("bindingpolicies", {"metadata": {"name": "platform-default"}, "spec": {"provisioners": [{"type": "postgres", "mode": "provision"}]}})
  state.create("bindingpolicies", {"metadata": {"name": "profile-ephemeral"}, "spec": {"profile": "ephemeral", "provisioners": [COMPOSE]}})
  return state


@pytest.fixture
def journal_path(tmp_path):
  return tmp_path / "journal.jsonl"


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def client(state, journal_path, tokens):
  return TestClient(create_app(state, Journal(journal_path), tokens.verifier(), teams=FakeTeams("team-alpha")))


@pytest.fixture
def as_(tokens):
  people = {
    "owner": dict(sub="owner-1", email="owner@example.com", group_paths=["/platform-users", "/teams/team-alpha"]),
    "outsider": dict(sub="out-1", email="out@example.com", group_paths=["/platform-users"]),
    "admin": dict(sub="admin-1", email="admin@example.com", group_paths=["/platform-admins", "/platform-users"]),
  }
  return lambda who: {"Authorization": f"Bearer {tokens.issue(**people[who])}"}


@pytest.fixture
def environment(client, as_):
  assert client.post("/v1/environments", json={"name": "demo", "profile": "ephemeral"}, headers=as_("owner")).status_code == 202
  return "demo"


def put(client, as_, provisioners, who="admin", name="demo"):
  return client.put(f"/v1/environments/{name}/binding-policy", json={"provisioners": provisioners}, headers=as_(who))


def test_get_without_policy_shows_the_default(client, as_, environment):
  response = client.get("/v1/environments/demo/binding-policy", headers=as_("owner"))
  assert response.status_code == 200
  assert response.json() == {
    "kind": "BindingPolicy", "environment": "demo", "provisioners": [],
    "profile": {"name": "ephemeral", "provisioners": [COMPOSE]},
    "default": [{"type": "postgres", "mode": "provision"}],
  }


def test_admin_sets_the_policy_owned_by_the_environment(client, as_, environment, state, journal_path):
  response = put(client, as_, [COMPOSE])
  assert response.status_code == 200
  assert response.json()["provisioners"] == [COMPOSE]
  policy = state.get("bindingpolicies", "env-demo")
  assert policy["spec"] == {"environment": "demo", "provisioners": [COMPOSE]}
  assert policy["metadata"]["ownerReferences"][0] | {"uid": None} == {"apiVersion": "platform.wasp.silvios.me/v1alpha1", "kind": "Environment", "name": "demo", "uid": None}
  records = [json.loads(line) for line in journal_path.read_text().splitlines()]
  assert [record.get("action") for record in records][-2:] == ["set-policy", None]
  assert client.get("/v1/environments/demo/binding-policy", headers=as_("owner")).json()["provisioners"] == [COMPOSE]


def test_set_again_replaces_and_empty_removes(client, as_, environment, state):
  put(client, as_, [COMPOSE])
  restored = {"type": "postgres", "class": "restored", "mode": "provision"}
  assert put(client, as_, [restored, COMPOSE]).json()["provisioners"] == [restored, COMPOSE]
  assert put(client, as_, []).json()["provisioners"] == []
  assert "env-demo" not in state.stores["bindingpolicies"]


def test_only_admins_write(client, as_, environment):
  response = put(client, as_, [COMPOSE], who="owner")
  assert response.status_code == 403


def test_only_users_of_the_environment_read(client, as_, environment):
  assert client.get("/v1/environments/demo/binding-policy", headers=as_("outsider")).status_code == 403
  assert client.get("/v1/environments/demo/binding-policy", headers=as_("admin")).status_code == 200


def test_unknown_environment(client, as_):
  assert put(client, as_, [COMPOSE], name="ghost").status_code == 404
  assert client.get("/v1/environments/ghost/binding-policy", headers=as_("admin")).status_code == 404


@pytest.mark.parametrize("item", [
  {"type": "postgres", "mode": "compose"},  # no shared instance
  {"type": "postgres", "mode": "compose", "params": {"instance": "shared_pg"}},
  {"type": "postgres", "mode": "migrate"},
  {"type": "Postgres", "mode": "provision"},
  {"type": "postgres", "class": "restored\n", "mode": "provision"},
  {"type": "postgres", "mode": "provision", "credential": "x"},
  {"type": "postgres", "class": "restored", "mode": "bind"},  # no params at all
  {**BIND, "params": {k: v for k, v in BIND["params"].items() if k != "secretRef"}},
  {**BIND, "params": {k: v for k, v in BIND["params"].items() if k != "host"}},
  {**BIND, "params": {**BIND["params"], "secretRef": "resource.demo.app.db"}},
  {**BIND, "params": {**BIND["params"], "host": "evil host"}},
  {**BIND, "params": {**BIND["params"], "port": "54x"}},
  {**BIND, "params": {**BIND["params"], "database": "a; DROP"}},
])
def test_invalid_items_are_refused(client, as_, environment, state, item):
  assert put(client, as_, [item]).status_code == 422
  assert "env-demo" not in state.stores["bindingpolicies"]


def test_bind_with_its_values_is_accepted(client, as_, environment, state):
  response = put(client, as_, [COMPOSE, BIND])
  assert response.status_code == 200, response.text
  assert state.get("bindingpolicies", "env-demo")["spec"]["provisioners"] == [COMPOSE, BIND]


def put_profile(client, as_, provisioners, who="admin", profile="ephemeral"):
  return client.put(f"/v1/profiles/{profile}/binding-policy", json={"provisioners": provisioners}, headers=as_(who))


def test_a_profile_policy_is_not_part_of_another_profile(client, as_):
  assert client.post("/v1/environments", json={"name": "lasting", "profile": "shared"}, headers=as_("owner")).status_code == 202
  body = client.get("/v1/environments/lasting/binding-policy", headers=as_("owner")).json()
  assert body["profile"] == {"name": "shared", "provisioners": []}
  assert body["default"] == [{"type": "postgres", "mode": "provision"}]


def test_anyone_signed_in_reads_a_profile_policy(client, as_):
  response = client.get("/v1/profiles/ephemeral/binding-policy", headers=as_("outsider"))
  assert response.status_code == 200
  assert response.json() == {"kind": "BindingPolicy", "profile": "ephemeral", "provisioners": [COMPOSE], "default": [{"type": "postgres", "mode": "provision"}]}


def test_admin_replaces_and_removes_a_profile_policy(client, as_, state, journal_path):
  provision = {"type": "postgres", "mode": "provision"}
  assert put_profile(client, as_, [provision]).json()["provisioners"] == [provision]
  assert state.get("bindingpolicies", "profile-ephemeral")["spec"] == {"profile": "ephemeral", "provisioners": [provision]}
  assert put_profile(client, as_, [COMPOSE], profile="shared").status_code == 200
  assert state.get("bindingpolicies", "profile-shared")["spec"] == {"profile": "shared", "provisioners": [COMPOSE]}
  assert put_profile(client, as_, []).json()["provisioners"] == []
  assert [obj["metadata"]["name"] for obj in state.list("bindingpolicies") if obj["metadata"]["name"] == "profile-ephemeral"] == []
  records = [json.loads(line) for line in journal_path.read_text().splitlines()]
  assert "set-policy" in [record.get("action") for record in records]


def test_only_admins_write_a_profile_policy(client, as_):
  response = put_profile(client, as_, [COMPOSE], who="owner")
  assert response.status_code == 403
  assert "set by platform-admins" in response.json()["error"]["message"]


def test_unknown_profile(client, as_):
  assert client.get("/v1/profiles/nope/binding-policy", headers=as_("owner")).status_code == 404
  response = put_profile(client, as_, [COMPOSE], profile="nope")
  assert response.status_code == 404
  assert "profiles: ephemeral, shared" in response.json()["error"]["message"]


def test_a_profile_policy_item_is_validated(client, as_):
  assert put_profile(client, as_, [{"type": "postgres", "mode": "compose"}]).status_code == 422
