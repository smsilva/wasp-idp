"""Each outcome of a Build, with GitHub simulated by httpx.MockTransport."""
import base64
import copy
import io
import json
import zipfile
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from scm_github_provider.build import BUILDING, RETENTION, RUN_LOOKUP, BuildReconciler, spec_errors, score_schema, version_name
from scm_github_provider.github import GitHubApp

from test_component_creation import NOW, FakeObjects, FakeSecrets, connection, conditions

REPO = "wasp-foundry/greeting-api"
REQUEST_ID = "d6654c40-359d-4839-b17a-10871bc3c245"
COMMIT = "86a7c0820fb72c59e93495a13c01e24cbb750936"
DIGEST = "sha256:" + "c" * 64
SEED_SPEC = (Path(__file__).parents[3] / "templates" / "python-service" / "content" / "app-spec.yaml").read_text()
# The seed renders ${{ values.* }}; a rendered app-spec.yaml carries the values.
APP_SPEC = SEED_SPEC.replace("${{ values.name }}", "greeting-api").replace("${{ values.port }}", "8000")


def zipped(files: dict[str, bytes]) -> bytes:
  buffer = io.BytesIO()
  with zipfile.ZipFile(buffer, "w") as archive:
    for name, content in files.items():
      archive.writestr(name, content)
  return buffer.getvalue()


def result(**changes) -> dict:
  return {
    "version": "0.3.0-greetings.86a7c08", "image": "ghcr.io/wasp-foundry/greeting-api", "digest": DIGEST,
    "commit": COMMIT, "branch": "feat/greetings", "requestId": REQUEST_ID, **changes,
  }


class FakeActions:
  """A repo with the platform-build workflow: the dispatch makes a run, which the test moves along."""

  def __init__(self):
    self.workflow = True
    self.branches = {"main", "feat/greetings"}
    self.runs = []
    self.artifacts = {"platform-build": zipped({"platform-build.json": json.dumps(result()).encode()})}
    self.files = {("app-spec.yaml", COMMIT): APP_SPEC.encode()}
    self.dispatches = []
    self.calls = []
    self.fail = {}  # "METHOD path suffix" -> status
    self.run_name = "platform-build {request_id}"

  def finish(self, conclusion="success"):
    for run in self.runs:
      run.update(status="completed", conclusion=conclusion)

  def handler(self, request: httpx.Request) -> httpx.Response:
    method, path = request.method, request.url.path
    self.calls.append(f"{method} {path}")
    for key, status in self.fail.items():
      if f"{method} {path}".endswith(key):
        return httpx.Response(status, json={"message": "nope"})
    if request.url.host == "blob.test":
      return httpx.Response(200, content=self.artifacts[path.strip("/")])
    if path.endswith("/access_tokens"):
      return httpx.Response(201, json={"token": "ghs_fake"})
    prefix = f"/repos/{REPO}/"
    assert path.startswith(prefix), path
    rest = path[len(prefix):]
    if rest == "actions/workflows/platform-build.yaml":
      return httpx.Response(200, json={"id": 1, "path": ".github/workflows/platform-build.yaml"}) if self.workflow else httpx.Response(404, json={"message": "Not Found"})
    if rest.startswith("branches/"):
      branch = rest.removeprefix("branches/").replace("%2F", "/")
      return httpx.Response(200, json={"name": branch}) if branch in self.branches else httpx.Response(404, json={"message": "Branch not found"})
    if method == "POST" and rest == "actions/workflows/platform-build.yaml/dispatches":
      body = json.loads(request.content)
      self.dispatches.append(body)
      run_id = 1000 + len(self.runs)
      self.runs.append({
        "id": run_id, "display_title": self.run_name.format(request_id=body["inputs"]["request-id"]), "head_branch": body["ref"],
        "head_sha": COMMIT, "status": "queued", "conclusion": None, "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}",
      })
      return httpx.Response(204)
    if rest == "actions/runs":
      assert request.url.params["event"] == "workflow_dispatch"
      branch = request.url.params["branch"]
      return httpx.Response(200, json={"workflow_runs": [run for run in reversed(self.runs) if run["head_branch"] == branch]})
    if rest.endswith("/artifacts") and rest.startswith("actions/runs/"):
      items = [{"id": index, "name": name, "expired": False} for index, name in enumerate(self.artifacts)]
      return httpx.Response(200, json={"artifacts": items})
    if rest.startswith("actions/artifacts/") and rest.endswith("/zip"):
      name = list(self.artifacts)[int(rest.split("/")[2])]
      return httpx.Response(302, headers={"location": f"https://blob.test/{name}"})
    if rest.startswith("contents/"):
      content = self.files.get((rest.removeprefix("contents/"), request.url.params["ref"]))
      if content is None:
        return httpx.Response(404, json={"message": "Not Found"})
      return httpx.Response(200, json={"type": "file", "content": base64.b64encode(content).decode()})
    return httpx.Response(404, json={"message": "Not Found"})

  def factory(self, app_id, key):
    return GitHubApp(app_id, key, transport=httpx.MockTransport(self.handler), base_url="https://api.github.test")


def build(version=None, name="greeting-api-a1b2c3"):
  spec = {"component": "greeting-api", "branch": "feat/greetings", "requestId": REQUEST_ID, "repo": REPO, "scmConnection": "wasp-foundry"}
  if version:
    spec["version"] = version
  return {"metadata": {"name": name, "uid": "uid-1"}, "spec": spec}


class World:
  def __init__(self, obj=None, ready=True, resources=()):
    self.github = FakeActions()
    self.builds = FakeObjects(obj or build())
    self.connections = FakeObjects(connection(ready))
    self.versions = FakeObjects()
    self.resources = FakeObjects(*({"metadata": {"name": name}, "spec": {"type": "postgres"}} for name in resources))
    self.now = NOW
    self.clock = 0.0
    self.restart()

  def restart(self):
    self.reconciler = BuildReconciler(
      self.builds, self.connections, self.versions, self.resources, FakeSecrets(),
      github_factory=self.github.factory, now=lambda: self.now, clock=lambda: self.clock,
    )

  def run(self, wait=3600, name="greeting-api-a1b2c3"):
    self.clock += wait
    self.reconciler.reconcile(self.builds.get(name))
    return (self.builds.get(name) or {}).get("status")


@pytest.fixture
def world():
  return World()


def ready(status):
  return conditions(status)["Ready"]


def test_dispatch_follow_and_register(world):
  status = world.run()
  assert world.github.dispatches == [{"ref": "feat/greetings", "inputs": {"request-id": REQUEST_ID}}]
  assert conditions(status)["Dispatched"] == ("True", "Dispatched")
  assert conditions(status)["Running"] == ("True", "Started")
  assert ready(status) == ("False", BUILDING)
  assert status["runUrl"] == f"https://github.com/{REPO}/actions/runs/1000"
  world.github.finish()
  status = world.run()
  assert ready(status) == ("True", "Registered")
  assert conditions(status)["Succeeded"] == ("True", "Built")
  assert conditions(status)["SpecValidated"] == ("True", "Valid")
  assert status["result"] == result()
  assert status["appSpec"] == {"resources": [{"name": "db", "type": "postgres"}, {"name": "dns", "type": "dns"}, {"name": "route", "type": "route"}]}
  version = world.versions.get("greeting-api.0.3.0-greetings.86a7c08")
  assert version["metadata"]["labels"] == {"platform.wasp.silvios.me/component": "greeting-api"}
  assert version["spec"] == {
    "component": "greeting-api", "version": "0.3.0-greetings.86a7c08", "image": "ghcr.io/wasp-foundry/greeting-api",
    "digest": DIGEST, "commit": COMMIT, "branch": "feat/greetings", "createdAt": "2026-10-11T12:00:00Z", "build": "greeting-api-a1b2c3",
  }
  assert len(world.github.dispatches) == 1


def test_the_requested_version_goes_to_the_workflow():
  world = World(build(version="1.0.0-rc.1"))
  world.github.artifacts["platform-build"] = zipped({"platform-build.json": json.dumps(result(version="1.0.0-rc.1")).encode()})
  world.run()
  assert world.github.dispatches[0]["inputs"] == {"request-id": REQUEST_ID, "version": "1.0.0-rc.1"}
  world.github.finish()
  assert ready(world.run()) == ("True", "Registered")
  assert world.versions.get("greeting-api.1.0.0-rc.1")["spec"]["version"] == "1.0.0-rc.1"


def test_a_version_other_than_the_requested_one_breaks_the_contract():
  world = World(build(version="1.0.0-rc.1"))
  world.run()
  world.github.finish()
  status = world.run()
  assert ready(status) == ("False", "ContractViolation")
  assert "the build asked for '1.0.0-rc.1'" in status["conditions"][-1]["message"]
  assert world.versions.items == {}


def test_waiting_runs_do_not_write_the_status_again(world):
  world.run()
  patches = len(world.builds.patches)
  world.run(wait=15)
  world.run(wait=15)
  assert len(world.builds.patches) == patches


def test_a_restart_after_the_dispatch_does_not_dispatch_again(world):
  world.reconciler._save = lambda *args: None  # the pass dies before its status is saved
  world.run()
  world.builds.items["greeting-api-a1b2c3"].pop("status", None)
  world.restart()
  world.run()
  assert len(world.github.dispatches) == 1


def test_no_workflow_is_workflow_not_found(world):
  world.github.workflow = False
  status = world.run()
  assert conditions(status)["Dispatched"] == ("False", "WorkflowNotFound")
  assert ready(status) == ("False", "WorkflowNotFound")
  assert "platform-build.yaml" in status["conditions"][-1]["message"]
  assert world.github.dispatches == []


def test_missing_branch_is_branch_not_found(world):
  world.github.branches = {"main"}
  assert ready(world.run()) == ("False", "BranchNotFound")
  assert world.github.dispatches == []


def test_a_workflow_without_the_inputs_breaks_the_contract(world):
  world.github.fail["/dispatches"] = 422
  assert ready(world.run()) == ("False", "ContractViolation")


def test_a_failed_run_is_build_failed_with_the_run_url(world):
  world.run()
  world.github.finish("failure")
  status = world.run()
  assert conditions(status)["Succeeded"] == ("False", "BuildFailed")
  assert ready(status) == ("False", "BuildFailed")
  assert status["runUrl"] in status["conditions"][-1]["message"]


def test_a_run_without_the_artifact_breaks_the_contract(world):
  world.github.artifacts = {"something-else": b""}
  world.run()
  world.github.finish()
  assert ready(world.run()) == ("False", "ContractViolation")
  assert world.versions.items == {}


@pytest.mark.parametrize("archive", [
  zipped({"other.json": b"{}"}),
  zipped({"platform-build.json": b"not json"}),
  zipped({"platform-build.json": json.dumps(result(digest="abc")).encode()}),
  zipped({"platform-build.json": json.dumps(result(requestId="someone-else")).encode()}),
  zipped({"platform-build.json": json.dumps({"version": "0.3.0"}).encode()}),
  zipped({"platform-build.json": json.dumps(result(version="0.3.0-.x")).encode()}),
  b"not a zip",
])
def test_an_invalid_artifact_breaks_the_contract(world, archive):
  world.github.artifacts["platform-build"] = archive
  world.run()
  world.github.finish()
  assert ready(world.run()) == ("False", "ContractViolation")


def test_a_run_that_never_shows_up_breaks_the_contract(world):
  world.github.run_name = "build {request_id}"
  status = world.run()
  assert conditions(status)["Running"] == ("False", "Queued")
  assert ready(status) == ("False", BUILDING)
  world.now = NOW + RUN_LOOKUP
  status = world.run()
  assert ready(status) == ("False", "ContractViolation")
  assert "run-name" in status["conditions"][-1]["message"]


def test_unknown_type_and_missing_id_are_invalid_spec(world):
  spec = APP_SPEC.replace("type: postgres", "type: redis\n  cache:\n    type: postgres\n    id: shared-cache")
  world.github.files[("app-spec.yaml", COMMIT)] = spec.encode()
  world.run()
  world.github.finish()
  status = world.run()
  assert conditions(status)["SpecValidated"] == ("False", "InvalidSpec")
  assert ready(status) == ("False", "InvalidSpec")
  assert {item["field"] for item in status["errors"]} == {"resources.db.type", "resources.cache.id"}
  assert world.versions.items == {}


def test_a_known_id_passes():
  world = World(resources=("shared-db",))
  world.github.files[("app-spec.yaml", COMMIT)] = (APP_SPEC.replace("type: postgres", "type: postgres\n    id: shared-db")).encode()
  world.run()
  world.github.finish()
  assert ready(world.run()) == ("True", "Registered")


def test_the_score_schema_is_checked(world):
  world.github.files[("app-spec.yaml", COMMIT)] = APP_SPEC.replace("apiVersion: score.dev/v1b1", "apiVersion: platform/v1").encode()
  world.run()
  world.github.finish()
  status = world.run()
  assert ready(status) == ("False", "InvalidSpec")
  assert [item["field"] for item in status["errors"]] == ["apiVersion"]


def test_no_app_spec_is_invalid_spec(world):
  world.github.files = {}
  world.run()
  world.github.finish()
  status = world.run()
  assert ready(status) == ("False", "InvalidSpec")
  assert status["errors"] == [{"field": "app-spec.yaml", "reason": "not found"}]


def test_the_same_version_from_another_commit_is_a_conflict(world):
  existing = {"metadata": {"name": "greeting-api.0.3.0-greetings.86a7c08", "resourceVersion": "1"},
              "spec": {"component": "greeting-api", "version": "0.3.0-greetings.86a7c08", "commit": "f" * 40}}
  world.versions = FakeObjects(existing)
  world.restart()
  world.run()
  world.github.finish()
  assert ready(world.run()) == ("False", "VersionConflict")
  assert world.versions.get(existing["metadata"]["name"])["spec"]["commit"] == "f" * 40


def test_the_same_commit_built_again_is_the_same_version(world):
  existing = {"metadata": {"name": "greeting-api.0.3.0-greetings.86a7c08", "resourceVersion": "1"},
              "spec": {"component": "greeting-api", "version": "0.3.0-greetings.86a7c08", "commit": COMMIT, "build": "older"}}
  world.versions = FakeObjects(existing)
  world.restart()
  world.run()
  world.github.finish()
  assert ready(world.run()) == ("True", "Registered")
  assert world.versions.get(existing["metadata"]["name"])["spec"]["build"] == "older"


def test_connection_not_ready_stops_before_github():
  world = World(ready=False)
  assert ready(world.run()) == ("False", "ConnectionNotReady")
  assert world.github.calls == []


def test_github_outage_backs_off_then_goes_on(world):
  world.run()
  world.github.fail["/actions/runs"] = 502
  status = world.run()
  assert ready(status) == ("False", "GitHubUnavailable")
  calls = world.github.calls.count(f"GET /repos/{REPO}/actions/runs")
  world.run(wait=1)  # inside the backoff: nothing happens
  assert world.github.calls.count(f"GET /repos/{REPO}/actions/runs") == calls
  del world.github.fail["/actions/runs"]
  world.github.finish()
  status = world.run()
  assert ready(status) == ("True", "Registered")
  assert len(world.github.dispatches) == 1


def test_the_installation_token_is_reused(world):
  world.run()
  world.run(wait=15)
  assert sum(call.endswith("/access_tokens") for call in world.github.calls) == 1


def test_ready_build_is_removed_after_retention_and_the_version_stays(world):
  world.run()
  world.github.finish()
  world.run()
  world.now = NOW + RETENTION
  world.run()
  assert world.builds.get("greeting-api-a1b2c3") is None
  assert world.versions.get("greeting-api.0.3.0-greetings.86a7c08") is not None


def test_spec_errors_of_the_seed_is_empty():
  errors, declared = spec_errors(APP_SPEC, score_schema(), ("postgres", "dns", "route"), lambda name: False)
  assert errors == []
  assert [item["type"] for item in declared] == ["postgres", "dns", "route"]


def test_version_name():
  assert version_name("greeting-api", "1.0.0-RC.1") == "greeting-api.1.0.0-rc.1"
