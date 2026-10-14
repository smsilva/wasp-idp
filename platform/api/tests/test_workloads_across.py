"""workload list across environments (#490): GET /v1/workloads, scoped like GET /v1/environments."""
import pytest

from test_workloads import admin, client, environment, journal_path, owner, state, teammate, tokens  # noqa: F401
from test_builds import bearer


@pytest.fixture
def stranger(tokens):
  return bearer(tokens, sub="user-9", teams=())


@pytest.fixture
def deployed(client, state, admin):
  # greeting-api in demo and in private, and an extra instance in demo.
  state.create("environments", environment("empty"))
  for path in ("demo/workloads/greeting-api", "private/workloads/greeting-api", "demo/workloads/greeting-canary"):
    body = {"version": "1.0.0", **({"component": "greeting-api"} if "canary" in path else {})}
    response = client.post(f"/v1/environments/{path}/revisions", json=body, headers=admin)
    assert response.status_code == 202, response.text
  state.create("components", {"metadata": {"name": "other-api"}, "spec": {"owner": "team-alpha"}})


def names(response):
  assert response.status_code == 200, response.text
  return [item["name"] for item in response.json()["items"]]


def test_owner_sees_their_environments(client, deployed, owner):
  assert names(client.get("/v1/workloads", headers=owner)) == ["greeting-api@demo", "greeting-canary@demo"]


def test_team_member_sees_the_shared_ones(client, deployed, teammate):
  assert names(client.get("/v1/workloads", headers=teammate)) == ["greeting-api@demo", "greeting-canary@demo"]


def test_admin_sees_every_environment_sorted(client, deployed, admin):
  assert names(client.get("/v1/workloads", headers=admin)) == ["greeting-api@demo", "greeting-canary@demo", "greeting-api@private"]


def test_stranger_sees_nothing(client, deployed, stranger):
  assert names(client.get("/v1/workloads", headers=stranger)) == []


def test_filters(client, deployed, admin):
  assert names(client.get("/v1/workloads", params={"environment": "private"}, headers=admin)) == ["greeting-api@private"]
  assert names(client.get("/v1/workloads", params={"component": "greeting-api", "environment": "demo"}, headers=admin)) == ["greeting-api@demo", "greeting-canary@demo"]
  assert names(client.get("/v1/workloads", params={"component": "other-api"}, headers=admin)) == []


def test_environment_filter_outside_the_scope(client, deployed, owner):
  assert client.get("/v1/workloads", params={"environment": "private"}, headers=owner).status_code == 403
  assert client.get("/v1/workloads", params={"environment": "nope"}, headers=owner).status_code == 404


def test_the_per_environment_route_stays(client, deployed, owner):
  assert names(client.get("/v1/environments/demo/workloads", headers=owner)) == ["greeting-api@demo", "greeting-canary@demo"]
