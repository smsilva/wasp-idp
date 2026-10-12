"""workload apply (#293): the plan of an environment, diffed against its instances."""
import pytest

from test_workload_specs import indexed
from test_workloads import admin, client, close, environment, journal_path, owner, state, teammate, tokens  # noqa: F401  (fixtures)

APPLY = "/v1/environments/demo/workloads:apply"


@pytest.fixture
def ratings(state):
  # A second component, owned by team-beta: the owner of demo is not in it.
  state.create("components", {"metadata": {"name": "ratings"}, "spec": {"owner": "team-beta", "system": "greeter"}})
  state.create("versions", indexed("ratings", "2.0.0", "2026-10-01T10:00:00Z", branch="main"))


def apply(client, headers, workloads, dry_run=False, prune=False):
  return client.post(APPLY, json={"workloads": workloads, "dryRun": dry_run, "prune": prune}, headers=headers)


def actions(body):
  return {item["instance"]: item["action"] for item in body["items"]}


def deployed(state, instance="greeting-api", number=1, reason="Succeeded"):
  """The provider closed the revision and keeps the instance."""
  close(state, f"demo.{instance}.{number}", "True" if reason == "Succeeded" else "False", reason)
  name = f"demo.{instance}"
  if reason == "Succeeded" and name not in state.stores["workloadinstances"]:
    state.create("workloadinstances", {
      "metadata": {"name": name},
      "spec": {"environment": "demo", "instance": instance, "component": instance},
      "status": {"revision": number, "conditions": [{"type": "Ready", "status": "True", "reason": "Available"}]},
    })


def test_dry_run_writes_nothing(client, state, owner):
  response = apply(client, owner, {"greeting-api": {"version": "1.0.0", "replicas": 2}}, dry_run=True)
  assert response.status_code == 200, response.text
  body = response.json()
  assert (body["environment"], body["applied"]) == ("demo", False)
  assert body["summary"] == {"add": 1, "change": 0, "remove": 0, "unchanged": 0}
  assert body["items"] == [{
    "instance": "greeting-api",
    "component": "greeting-api",
    "action": "add",
    "from": None,
    "to": {"version": "1.0.0", "replicas": 2},
    "revision": None,
  }]
  assert state.stores["workloadrevisions"] == {}


def test_dry_run_is_the_default(client, state, owner):
  response = client.post(APPLY, json={"workloads": {"greeting-api": {"version": "1.0.0"}}}, headers=owner)
  assert response.json()["applied"] is False
  assert state.stores["workloadrevisions"] == {}


def test_apply_writes_one_revision_per_change(client, state, owner, journal_path):
  response = apply(client, owner, {"greeting-api": {"version": "1.0.0", "replicas": 2}})
  assert response.status_code == 200, response.text
  body = response.json()
  assert body["applied"] is True
  assert body["items"][0]["revision"] == 1
  spec = state.get("workloadrevisions", "demo.greeting-api.1")["spec"]
  assert (spec["action"], spec["version"], spec["overrides"]) == ("deploy", "1.0.0", {"replicas": 2})
  assert '"WorkloadRevision"' in journal_path.read_text()


def test_same_plan_again_is_unchanged(client, state, owner):
  apply(client, owner, {"greeting-api": {"version": "1.0.0", "replicas": 1}})
  # Still open counts as wanted: the provider is on it.
  assert actions(apply(client, owner, {"greeting-api": {"version": "1.0.0"}}).json()) == {"greeting-api": "unchanged"}
  deployed(state)
  body = apply(client, owner, {"greeting-api": {"version": "1.0.0"}}).json()
  assert body["summary"] == {"add": 0, "change": 0, "remove": 0, "unchanged": 1}
  assert body["items"][0]["revision"] is None
  assert len(state.stores["workloadrevisions"]) == 1


def test_new_version_or_replicas_is_a_change(client, state, owner):
  apply(client, owner, {"greeting-api": {"version": "1.0.0"}})
  deployed(state)
  body = apply(client, owner, {"greeting-api": {"version": "1.0.0", "replicas": 3}}, dry_run=True).json()
  assert body["items"][0]["action"] == "change"
  assert (body["items"][0]["from"], body["items"][0]["to"]) == ({"version": "1.0.0", "replicas": 1}, {"version": "1.0.0", "replicas": 3})
  body = apply(client, owner, {"greeting-api": {"branch": "feat/greetings"}}).json()
  # The branch is pinned to its newest version.
  assert (body["items"][0]["action"], body["items"][0]["to"]["version"], body["items"][0]["revision"]) == ("change", "1.1.0-greetings.2", 2)


def test_failed_newest_revision_is_tried_again(client, state, owner):
  apply(client, owner, {"greeting-api": {"version": "1.0.0"}})
  deployed(state)
  apply(client, owner, {"greeting-api": {"version": "1.1.0-greetings.1"}})
  deployed(state, number=2, reason="RolloutFailed")
  body = apply(client, owner, {"greeting-api": {"version": "1.1.0-greetings.1"}}).json()
  assert (body["items"][0]["action"], body["items"][0]["revision"]) == ("change", 3)


def test_removed_instance_is_added_again(client, state, owner):
  apply(client, owner, {"greeting-api": {"version": "1.0.0"}})
  deployed(state)
  client.delete("/v1/environments/demo/workloads/greeting-api", headers=owner)
  close(state, "demo.greeting-api.2", "True", "Succeeded")
  del state.stores["workloadinstances"]["demo.greeting-api"]
  assert actions(apply(client, owner, {"greeting-api": {"version": "1.0.0"}}).json()) == {"greeting-api": "add"}


def test_without_prune_others_stay(client, state, owner):
  apply(client, owner, {"greeting-api": {"version": "1.0.0"}})
  deployed(state)
  body = apply(client, owner, {}).json()
  assert body["items"] == []
  assert body["summary"] == {"add": 0, "change": 0, "remove": 0, "unchanged": 0}


def test_prune_removes_what_the_plan_leaves_out(client, state, owner):
  apply(client, owner, {"greeting-api": {"version": "1.0.0"}})
  deployed(state)
  body = apply(client, owner, {}, prune=True).json()
  assert actions(body) == {"greeting-api": "remove"}
  assert (body["items"][0]["from"], body["items"][0]["to"], body["items"][0]["revision"]) == ({"version": "1.0.0", "replicas": 1}, None, 2)
  assert state.get("workloadrevisions", "demo.greeting-api.2")["spec"]["action"] == "remove"
  # The remove is still open: pruning again writes nothing new.
  assert apply(client, owner, {}, prune=True).json()["items"] == []


def test_a_denied_instance_applies_nothing(client, state, owner, ratings):
  response = apply(client, owner, {"greeting-api": {"version": "1.0.0"}, "ratings": {"version": "2.0.0"}})
  assert response.status_code == 403
  assert "only members of its owner team (team-beta)" in response.json()["error"]["message"]
  assert state.stores["workloadrevisions"] == {}


def test_prune_needs_the_owner_team_too(client, state, owner, admin, ratings):
  apply(client, admin, {"ratings": {"version": "2.0.0"}})
  deployed(state, instance="ratings")
  response = apply(client, owner, {"greeting-api": {"version": "1.0.0"}}, prune=True)
  assert response.status_code == 403
  assert "remove of 'ratings'" in response.json()["error"]["message"]
  assert list(state.stores["workloadrevisions"]) == ["demo.ratings.1"]


def test_admin_applies_any_component(client, state, admin, ratings):
  body = apply(client, admin, {"greeting-api": {"version": "1.0.0"}, "ratings": {"version": "2.0.0"}}).json()
  assert actions(body) == {"greeting-api": "add", "ratings": "add"}
  assert set(state.stores["workloadrevisions"]) == {"demo.greeting-api.1", "demo.ratings.1"}


@pytest.mark.parametrize("workloads,status,message", [
  ({"greeting-api": {"version": "2.0.0"}}, 404, "no version 2.0.0 in the index"),
  ({"greeting-api": {"version": "0.9.0"}}, 409, "SpecNotIndexed"),
  ({"greeting-api": {}}, 422, "either version or branch"),
  ({"greeting-api": {"version": "1.0.0", "branch": "main"}}, 422, "either version or branch"),
  ({"greeting-api": {"version": "latest"}}, 422, "major"),
  ({"greeting-api": {"version": "1.0.0", "replicas": 50}}, 422, "replicas"),
  ({"greeting-api": {"version": "1.0.0", "image": "x"}}, 422, "image"),
  ({"Greeting_API": {"version": "1.0.0"}}, 422, "not an instance name"),
  ({"unknown": {"version": "1.0.0"}}, 404, "component 'unknown' not found"),
])
def test_refusals_apply_nothing(client, state, owner, workloads, status, message):
  response = apply(client, owner, workloads)
  assert response.status_code == status, response.text
  assert message in response.json()["error"]["message"]
  assert state.stores["workloadrevisions"] == {}


def test_component_equal_to_the_key_is_accepted(client, owner):
  assert apply(client, owner, {"greeting-api": {"component": "greeting-api", "version": "1.0.0"}}).status_code == 200


def test_extra_instance_in_the_plan(client, state, owner):
  body = apply(client, owner, {"greeting-api": {"version": "1.0.0"}, "greeting-api-pr-1": {"component": "greeting-api", "branch": "feat/greetings"}}).json()
  assert [(item["instance"], item["component"], item["action"]) for item in body["items"]] == [
    ("greeting-api", "greeting-api", "add"),
    ("greeting-api-pr-1", "greeting-api", "add"),
  ]
  assert state.get("workloadrevisions", "demo.greeting-api-pr-1.1")["spec"]["component"] == "greeting-api"


def test_plan_keeps_the_component_of_an_instance(client, state, owner, ratings):
  apply(client, owner, {"greeting-api-pr-1": {"component": "greeting-api", "version": "1.0.0"}})
  deployed(state, "greeting-api-pr-1")
  # Without component, the plan means the component named after the key, which this instance does not run.
  response = apply(client, owner, {"greeting-api-pr-1": {"version": "1.0.0"}})
  assert response.status_code == 409
  assert "runs component 'greeting-api'" in response.json()["error"]["message"]
  assert list(state.stores["workloadrevisions"]) == ["demo.greeting-api-pr-1.1"]


def test_prune_removes_an_extra_instance(client, state, owner):
  apply(client, owner, {"greeting-api": {"version": "1.0.0"}, "greeting-api-pr-1": {"component": "greeting-api", "version": "1.0.0"}})
  deployed(state)
  deployed(state, "greeting-api-pr-1")
  body = apply(client, owner, {"greeting-api": {"version": "1.0.0"}}, prune=True).json()
  assert actions(body) == {"greeting-api": "unchanged", "greeting-api-pr-1": "remove"}
  assert state.get("workloadrevisions", "demo.greeting-api-pr-1.2")["spec"]["component"] == "greeting-api"


def test_apply_needs_can_use(client, owner):
  response = client.post("/v1/environments/private/workloads:apply", json={"workloads": {}}, headers=owner)
  assert response.status_code == 403
  assert client.post("/v1/environments/nope/workloads:apply", json={"workloads": {}}, headers=owner).status_code == 404


def test_concurrent_write_reports_what_was_applied(client, state, admin, ratings, monkeypatch):
  # Another request takes revision 1 of ratings after the plan was made.
  created = state.create

  def racing(plural, body):
    if body["metadata"]["name"] == "demo.ratings.1" and "demo.ratings.1" not in state.stores[plural]:
      created(plural, body)
    return created(plural, body)

  monkeypatch.setattr(state, "create", racing)
  response = apply(client, admin, {"greeting-api": {"version": "1.0.0"}, "ratings": {"version": "2.0.0"}})
  assert response.status_code == 409
  message = response.json()["error"]["message"]
  assert "taken by a concurrent request" in message
  assert "1 applied before it" in message


def test_a_resource_class_the_plan_leaves_out_is_a_change(client, state, owner):
  # Applying it takes the instance back to the plain resources.
  client.post("/v1/environments/demo/workloads/greeting-api/revisions", json={"version": "1.0.0", "resourceClasses": {"db": "restored"}}, headers=owner)
  body = client.post(APPLY, json={"workloads": {"greeting-api": {"version": "1.0.0"}}}, headers=owner).json()
  item = body["items"][0]
  assert (item["action"], item["from"], item["to"]) == ("change", {"version": "1.0.0", "replicas": 1, "resourceClasses": {"db": "restored"}}, {"version": "1.0.0", "replicas": 1})


@pytest.mark.parametrize("classes,action", [
  ({"db": "restored"}, "unchanged"),
  ({"db": "other"}, "change"),
])
def test_resource_classes_in_the_plan_are_diffed(client, state, owner, classes, action):
  client.post("/v1/environments/demo/workloads/greeting-api/revisions", json={"version": "1.0.0", "resourceClasses": {"db": "restored"}}, headers=owner)
  item = apply(client, owner, {"greeting-api": {"version": "1.0.0", "resourceClasses": classes}}, dry_run=True).json()["items"][0]
  assert (item["action"], item["to"]) == (action, {"version": "1.0.0", "replicas": 1, "resourceClasses": classes})


def test_apply_writes_the_resource_classes(client, state, owner):
  apply(client, owner, {"greeting-api": {"version": "1.0.0", "replicas": 2, "resourceClasses": {"db": "restored"}}})
  spec = state.get("workloadrevisions", "demo.greeting-api.1")["spec"]
  assert spec["overrides"] == {"replicas": 2, "resources": {"db": {"class": "restored"}}}


def test_empty_resource_classes_are_none(client, state, owner):
  apply(client, owner, {"greeting-api": {"version": "1.0.0"}})
  deployed(state)
  item = apply(client, owner, {"greeting-api": {"version": "1.0.0", "resourceClasses": {}}}, dry_run=True).json()["items"][0]
  assert (item["action"], item["to"]) == ("unchanged", {"version": "1.0.0", "replicas": 1})


@pytest.mark.parametrize("classes,message", [
  ({"cache": "restored"}, "apply of 'greeting-api': 1.0.0 has no resource 'cache'"),
  ({"db": "Not_Valid"}, "not a valid name"),
])
def test_resource_classes_refusals_apply_nothing(client, state, owner, classes, message):
  response = apply(client, owner, {"greeting-api": {"version": "1.0.0", "resourceClasses": classes}})
  assert response.status_code == 422, response.text
  assert message in response.json()["error"]["message"]
  assert state.stores["workloadrevisions"] == {}
