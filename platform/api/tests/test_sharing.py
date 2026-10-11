"""Environment sharing with teams (ADR 0026, #232)."""
import json

import pytest
from fastapi.testclient import TestClient

from platform_api.app import create_app
from platform_api.journal import Journal
from fakes import ADMIN_KUBECONFIG, FakeState, FakeTeams
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
def teams():
  return FakeTeams("team-alpha", "team-beta")


@pytest.fixture
def client(state, journal_path, tokens, teams):
  return TestClient(create_app(state, Journal(journal_path), tokens.verifier(), teams=teams))


@pytest.fixture
def as_(tokens):
  people = {
    "owner": dict(sub="owner-1", email="owner@example.com", group_paths=["/platform-users", "/teams/team-alpha"]),
    "teammate": dict(sub="mate-1", email="mate@example.com", group_paths=["/platform-users", "/teams/team-alpha"]),
    "outsider": dict(sub="out-1", email="out@example.com", group_paths=["/platform-users", "/teams/team-beta"]),
    "admin": dict(sub="admin-1", email="admin@example.com", group_paths=["/platform-admins", "/platform-users"]),
    # Same names as the team and as the admin group, but outside /teams and nested: never trusted.
    "homonym": dict(sub="hom-1", email="hom@example.com", group_paths=["/platform-users", "/ops/team-alpha", "/ops/platform-admins"]),
  }
  return lambda who: {"Authorization": f"Bearer {tokens.issue(**people[who])}"}


def ready(state, name):
  state.objects[name]["status"] = {"port": 7100, "kubeconfigData": ADMIN_KUBECONFIG, "conditions": [{"type": "Ready", "status": "True"}]}


def create(client, as_, name="shared-env", who="owner", **extra):
  return client.post("/v1/environments", json={"name": name, "profile": "ephemeral", **extra}, headers=as_(who))


def test_create_shared_with_own_team(client, as_, state):
  response = create(client, as_, sharedWith=["team-alpha"])
  assert response.status_code == 202
  assert response.json()["sharedWith"] == ["team-alpha"]
  assert response.json()["owner"] == "owner@example.com"
  assert state.objects["shared-env"]["spec"]["sharedWith"] == ["team-alpha"]


def test_private_by_default(client, as_, state):
  create(client, as_)
  assert "sharedWith" not in state.objects["shared-env"]["spec"]
  assert client.get("/v1/environments/shared-env", headers=as_("owner")).json()["sharedWith"] == []


def test_owner_cannot_share_with_a_team_they_are_not_in(client, as_, state):
  response = create(client, as_, sharedWith=["team-beta"])
  assert response.status_code == 403
  assert "team-beta" in response.json()["error"]["message"]
  assert "shared-env" not in state.objects


def test_admin_shares_with_any_team(client, as_):
  assert create(client, as_, who="admin", sharedWith=["team-beta"]).status_code == 202


def test_unknown_team_is_refused(client, as_):
  response = create(client, as_, who="admin", sharedWith=["team-ghost"])
  assert response.status_code == 422
  assert "team-ghost" in response.json()["error"]["message"]


def test_non_member_cannot_probe_unknown_teams(client, as_):
  # 403, not 422: a non-member learns nothing about which teams exist.
  assert create(client, as_, sharedWith=["team-ghost"]).status_code == 403


@pytest.mark.parametrize("team", ["Team", "team_alpha", "team-\n"])
def test_invalid_team_names_are_refused(client, as_, team):
  assert create(client, as_, sharedWith=[team]).status_code == 422


def test_teammate_gets_kubeconfig_outsider_does_not(client, as_, state):
  create(client, as_, sharedWith=["team-alpha"])
  ready(state, "shared-env")
  assert "kubeconfigData" in client.get("/v1/environments/shared-env", headers=as_("teammate")).json()
  assert "kubeconfigData" not in client.get("/v1/environments/shared-env", headers=as_("outsider")).json()


def test_teammate_cannot_delete_nor_share(client, as_, state):
  create(client, as_, sharedWith=["team-alpha"])
  assert client.delete("/v1/environments/shared-env", headers=as_("teammate")).status_code == 403
  assert client.put("/v1/environments/shared-env/shares/team-alpha", headers=as_("teammate")).status_code == 403
  assert client.delete("/v1/environments/shared-env/shares/team-alpha", headers=as_("teammate")).status_code == 403
  assert "shared-env" in state.objects


def test_share_and_unshare(client, as_, state, journal_path):
  create(client, as_)
  ready(state, "shared-env")
  response = client.put("/v1/environments/shared-env/shares/team-alpha", headers=as_("owner"))
  assert response.status_code == 200
  assert response.json()["sharedWith"] == ["team-alpha"]
  assert "kubeconfigData" in client.get("/v1/environments/shared-env", headers=as_("teammate")).json()
  # Sharing twice changes nothing.
  assert client.put("/v1/environments/shared-env/shares/team-alpha", headers=as_("owner")).json()["sharedWith"] == ["team-alpha"]
  response = client.delete("/v1/environments/shared-env/shares/team-alpha", headers=as_("owner"))
  assert response.status_code == 200
  assert response.json()["sharedWith"] == []
  assert "sharedWith" not in state.objects["shared-env"]["spec"]
  assert "kubeconfigData" not in client.get("/v1/environments/shared-env", headers=as_("teammate")).json()
  # The provider's status survives the spec change.
  assert state.objects["shared-env"]["status"]["kubeconfigData"] == ADMIN_KUBECONFIG
  entries = [json.loads(line) for line in journal_path.read_text().splitlines()]
  assert [(e["action"], e["spec"]) for e in entries if "action" in e][1:] == [("share", {"team": "team-alpha"}), ("unshare", {"team": "team-alpha"})]


def test_owner_cannot_share_with_foreign_team_later(client, as_):
  create(client, as_)
  assert client.put("/v1/environments/shared-env/shares/team-beta", headers=as_("owner")).status_code == 403


def test_unshare_a_team_the_owner_left(client, as_, state):
  create(client, as_, who="admin", sharedWith=["team-beta"])
  state.objects["shared-env"]["metadata"]["annotations"]["platform.wasp.silvios.me/owner"] = "owner-1"
  assert client.delete("/v1/environments/shared-env/shares/team-beta", headers=as_("owner")).status_code == 200


def test_unshare_not_shared_is_not_found(client, as_):
  create(client, as_)
  assert client.delete("/v1/environments/shared-env/shares/team-alpha", headers=as_("owner")).status_code == 404


def test_share_unknown_environment(client, as_):
  assert client.put("/v1/environments/missing/shares/team-alpha", headers=as_("owner")).status_code == 404


def test_list_shows_mine_and_my_teams(client, as_):
  create(client, as_, name="mine-private")
  create(client, as_, name="mine-shared", sharedWith=["team-alpha"])
  create(client, as_, name="beta-env", who="outsider", sharedWith=["team-beta"])
  names = lambda who, query="": [item["name"] for item in client.get(f"/v1/environments{query}", headers=as_(who)).json()["items"]]
  assert names("owner") == ["mine-private", "mine-shared"]
  assert names("teammate") == ["mine-shared"]
  assert names("outsider") == ["beta-env"]
  assert names("outsider", "?all=true") == ["beta-env", "mine-private", "mine-shared"]
  assert names("admin") == ["beta-env", "mine-private", "mine-shared"]


def test_list_never_carries_kubeconfig(client, as_, state):
  create(client, as_, sharedWith=["team-alpha"])
  ready(state, "shared-env")
  for item in client.get("/v1/environments?all=true", headers=as_("teammate")).json()["items"]:
    assert "kubeconfigData" not in item


def test_sharing_needs_teams(state, journal_path, tokens, as_):
  client = TestClient(create_app(state, Journal(journal_path), tokens.verifier()))
  assert create(client, as_, sharedWith=["team-alpha"]).status_code == 503
  assert create(client, as_).status_code == 202


def test_keycloak_down_blocks_sharing(client, as_, teams):
  teams.down = True
  assert create(client, as_, sharedWith=["team-alpha"]).status_code == 503


def test_homonym_groups_grant_nothing(client, as_, state):
  create(client, as_, sharedWith=["team-alpha"])
  ready(state, "shared-env")
  assert "kubeconfigData" not in client.get("/v1/environments/shared-env", headers=as_("homonym")).json()
  assert client.get("/v1/environments", headers=as_("homonym")).json()["items"] == []
  assert client.delete("/v1/environments/shared-env", headers=as_("homonym")).status_code == 403
  assert create(client, as_, name="hom-env", who="homonym", sharedWith=["team-alpha"]).status_code == 403


def test_me_lists_teams(client, as_):
  me = client.get("/v1/me", headers=as_("owner")).json()
  assert me["groups"] == ["platform-users", "team-alpha"]
  assert me["teams"] == ["team-alpha"]
