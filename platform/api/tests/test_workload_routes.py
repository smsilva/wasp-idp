"""workload route (#344, ADR 0035): the API writes the WorkloadRoute, the provider the HTTPRoute."""
import json

import pytest

from test_workload_apply import apply, deployed
from test_workloads import DEPLOY, admin, client, close, environment, journal_path, owner, state, teammate, tokens  # noqa: F401  (fixtures)

ROUTE = "/v1/environments/demo/workloads/routes/greeting-api"
SANDBOX = {"match": {"header": {"name": "x-sandbox", "value": "pr-42"}}, "to": "greeting-api-pr-42"}


@pytest.fixture
def sandbox(client, state, owner):
  """greeting-api and its sandbox greeting-api-pr-42 running in demo, and another component next to them."""
  client.post(DEPLOY, json={"version": "1.0.0"}, headers=owner)
  deployed(state)
  client.post("/v1/environments/demo/workloads/greeting-api-pr-42/revisions", json={"component": "greeting-api", "version": "1.0.0"}, headers=owner)
  close(state, "demo.greeting-api-pr-42.1", "True", "Succeeded")
  state.create("workloadinstances", {
    "metadata": {"name": "demo.greeting-api-pr-42"},
    "spec": {"environment": "demo", "instance": "greeting-api-pr-42", "component": "greeting-api"},
    "status": {"revision": 1, "conditions": [{"type": "Ready", "status": "True", "reason": "Available"}]},
  })
  state.create("components", {"metadata": {"name": "ratings"}, "spec": {"owner": "team-alpha", "system": "greeter"}})
  state.create("versions", {
    "metadata": {"name": "ratings.1.0.0"},
    "spec": {**state.get("versions", "greeting-api.1.0.0")["spec"], "component": "ratings"},
  })
  client.post("/v1/environments/demo/workloads/ratings/revisions", json={"version": "1.0.0"}, headers=owner)
  deployed(state, "ratings")
  return state


def test_put_writes_the_route(client, sandbox, owner, journal_path):
  response = client.put(ROUTE, json={"rules": [SANDBOX]}, headers=owner)
  assert response.status_code == 200, response.text
  assert response.json()["rules"] == [SANDBOX]
  obj = sandbox.get("workloadroutes", "demo.greeting-api")
  assert obj["spec"] == {"environment": "demo", "component": "greeting-api", "rules": [SANDBOX]}
  assert obj["metadata"]["labels"] == {"platform.wasp.silvios.me/environment": "demo", "platform.wasp.silvios.me/component": "greeting-api"}
  assert obj["metadata"]["ownerReferences"][0]["uid"] == sandbox.get("environments", "demo")["metadata"]["uid"]
  record = [json.loads(line) for line in journal_path.read_text().splitlines()][-2]
  assert (record["action"], record["kind"], record["name"]) == ("create", "WorkloadRoute", "demo.greeting-api")


def test_put_replaces_the_rules_and_keeps_the_finalizer(client, sandbox, owner):
  client.put(ROUTE, json={"rules": [SANDBOX]}, headers=owner)
  sandbox.stores["workloadroutes"]["demo.greeting-api"]["metadata"]["finalizers"] = ["platform.wasp.silvios.me/httproute"]
  weights = {"weights": {"greeting-api-pr-42": 10, "greeting-api": 90}}
  assert client.put(ROUTE, json={"rules": [weights]}, headers=owner).status_code == 200
  obj = sandbox.get("workloadroutes", "demo.greeting-api")
  assert obj["spec"]["rules"] == [weights]
  assert obj["metadata"]["finalizers"] == ["platform.wasp.silvios.me/httproute"]


def test_list_shows_the_traffic(client, sandbox, owner):
  items = {item["instance"]: item["traffic"] for item in client.get("/v1/environments/demo/workloads", headers=owner).json()["items"]}
  assert items == {"greeting-api": None, "greeting-api-pr-42": None, "ratings": None}
  rules = [SANDBOX, {"match": {"baggage": {"key": "sandbox", "value": "pr-42"}}, "to": "greeting-api-pr-42"}, {"weights": {"greeting-api-pr-42": 10, "greeting-api": 90}}]
  client.put(ROUTE, json={"rules": rules}, headers=owner)
  items = {item["instance"]: item["traffic"] for item in client.get("/v1/environments/demo/workloads", headers=owner).json()["items"]}
  assert items == {"greeting-api": "90%", "greeting-api-pr-42": "x-sandbox=pr-42, baggage sandbox=pr-42, 10%", "ratings": None}
  client.put(ROUTE, json={"rules": [SANDBOX]}, headers=owner)
  assert client.get("/v1/environments/demo/workloads/greeting-api", headers=owner).json()["traffic"] == "default"


def test_get_and_delete(client, sandbox, owner, teammate):
  assert client.get(ROUTE, headers=owner).status_code == 404
  client.put(ROUTE, json={"rules": [SANDBOX]}, headers=owner)
  # Reading needs can_use only.
  body = client.get(ROUTE, headers=teammate).json()
  assert (body["name"], body["status"], body["rules"]) == ("demo.greeting-api", "Pending", [SANDBOX])
  assert client.delete(ROUTE, headers=teammate).status_code == 403
  assert client.delete(ROUTE, headers=owner).status_code == 202
  assert "demo.greeting-api" not in sandbox.stores["workloadroutes"]
  assert client.delete(ROUTE, headers=owner).status_code == 404


@pytest.mark.parametrize("rules,status,message", [
  ([{**SANDBOX, "to": "ratings"}], 409, "ratings@demo runs component 'ratings'"),
  ([{**SANDBOX, "to": "nope"}], 409, "no instance 'nope'"),
  ([{"weights": {"greeting-api-pr-42": 10, "greeting-api": 80}}], 422, "add up to 90"),
  ([{"weights": {"greeting-api-pr-42": 10, "greeting-api": 90}}, SANDBOX], 422, "must be the last one"),
  ([SANDBOX, {**SANDBOX, "match": {"header": {"name": "X-Sandbox", "value": "pr-42"}}}], 422, "two rules match on header x-sandbox=pr-42"),
  ([{**SANDBOX, "match": {"header": {"name": "x-sandbox", "value": "pr 42"}}}], 422, "letters, digits"),
  ([{**SANDBOX, "match": {"baggage": {"key": "sandbox", "value": ".*"}}}], 422, "letters, digits"),
  ([{**SANDBOX, "match": {}}], 422, "either header or baggage"),
  ([{"to": "greeting-api-pr-42"}], 422, "either match and to, or weights"),
  ([{"weights": {"greeting-api": 100}, "to": "greeting-api"}], 422, "no match nor to"),
  ([], 422, "at least 1"),
])
def test_put_refusals(client, sandbox, owner, rules, status, message):
  response = client.put(ROUTE, json={"rules": rules}, headers=owner)
  assert response.status_code == status, response.text
  assert message in response.json()["error"]["message"]
  assert sandbox.list("workloadroutes") == []


def test_put_needs_the_main_instance(client, sandbox, owner):
  client.delete("/v1/environments/demo/workloads/greeting-api", headers=owner)
  response = client.put(ROUTE, json={"rules": [SANDBOX]}, headers=owner)
  assert response.status_code == 409
  assert "main instance greeting-api@demo is not deployed" in response.json()["error"]["message"]


def test_put_needs_the_owner_team(client, sandbox, teammate, admin):
  response = client.put(ROUTE, json={"rules": [SANDBOX]}, headers=teammate)
  assert response.status_code == 403
  assert "owner team (team-alpha)" in response.json()["error"]["message"]
  assert client.put(ROUTE, json={"rules": [SANDBOX]}, headers=admin).status_code == 200


def test_put_bad_names(client, sandbox, owner):
  assert client.put("/v1/environments/demo/workloads/routes/Greeting", json={"rules": [SANDBOX]}, headers=owner).status_code == 422
  assert client.put("/v1/environments/private/workloads/routes/greeting-api", json={"rules": [SANDBOX]}, headers=owner).status_code == 403


def test_remove_of_a_routed_instance_is_a_conflict(client, sandbox, owner):
  client.put(ROUTE, json={"rules": [SANDBOX]}, headers=owner)
  response = client.delete("/v1/environments/demo/workloads/greeting-api-pr-42", headers=owner)
  assert response.status_code == 409
  assert "sends traffic to it" in response.json()["error"]["message"]
  response = client.delete("/v1/environments/demo/workloads/greeting-api", headers=owner)
  assert response.status_code == 409
  assert "main instance of the route" in response.json()["error"]["message"]
  # Another component is not affected.
  assert client.delete("/v1/environments/demo/workloads/ratings", headers=owner).status_code == 202
  client.delete(ROUTE, headers=owner)
  assert client.delete("/v1/environments/demo/workloads/greeting-api-pr-42", headers=owner).status_code == 202


def test_prune_of_a_routed_instance_is_refused_before_any_write(client, sandbox, owner):
  client.put(ROUTE, json={"rules": [SANDBOX]}, headers=owner)
  before = len(sandbox.list("workloadrevisions"))
  response = apply(client, owner, {"greeting-api": {"version": "1.1.0-greetings.1"}, "ratings": {"version": "1.0.0"}}, prune=True)
  assert response.status_code == 409
  assert "prune of greeting-api-pr-42@demo" in response.json()["error"]["message"]
  assert len(sandbox.list("workloadrevisions")) == before
