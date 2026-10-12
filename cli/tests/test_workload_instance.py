"""workload deploy|list|get|history (#292): revisions of an instance, <instance>@<environment>."""
import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app

runner = CliRunner()


def revision(number=1, status="Pending", open_=True, message=None, action="deploy", version="2.1.0"):
  return {
    "kind": "WorkloadRevision", "name": f"demo.reviews.{number}", "environment": "demo", "instance": "reviews", "component": "reviews",
    "revision": number, "action": action, "version": version, "replicas": 2, "status": status, "open": open_, "message": message,
    "requestedBy": "dev@example.com", "createdAt": "2026-10-11T12:00:00Z",
  }


INSTANCE = {
  "kind": "WorkloadInstance", "name": "reviews@demo", "environment": "demo", "instance": "reviews", "component": "reviews",
  "version": "2.1.0", "image": "ghcr.io/acme/reviews@sha256:" + "b" * 64, "revision": 1, "status": "Available", "message": "2/2 replicas ready",
  "replicas": {"desired": 2, "ready": 2}, "url": "http://reviews.apps:80", "latestRevision": revision(status="Succeeded", open_=False),
  "resources": [{"name": "db", "type": "postgres", "mode": "provision", "status": "Ready"}],
}


@pytest.fixture
def api(monkeypatch):
  state = {"requests": [], "history": [[revision(status="Succeeded", open_=False, message="2/2 replicas available")]], "error": None}

  def handler(request: httpx.Request) -> httpx.Response:
    state["requests"].append(request)
    if state["error"]:
      return httpx.Response(state["error"][0], json={"error": {"code": "x", "message": state["error"][1]}})
    path = request.url.path
    if request.method == "POST":
      return httpx.Response(202, json=state.get("created") or revision())
    if request.method == "DELETE":
      return httpx.Response(202, json=revision(2, action="remove", version=None))
    if path.endswith("/revisions"):
      items = state["history"].pop(0) if len(state["history"]) > 1 else state["history"][0]
      return httpx.Response(200, json={"items": items})
    if path.endswith("/workloads"):
      return httpx.Response(200, json={"items": [INSTANCE]})
    return httpx.Response(200, json=state.get("instance") or INSTANCE)

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  monkeypatch.setattr("wasp_platform.commands.workload.time.sleep", lambda seconds: None)
  return state


def run(*args):
  return runner.invoke(app, ["workload", *args])


def test_deploy_writes_a_revision(api):
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--version", "2.1.0", "--replicas", "2")
  assert result.exit_code == 0, result.output
  request = api["requests"][0]
  assert request.url.path == "/v1/environments/demo/workloads/reviews/revisions"
  assert json.loads(request.content) == {"version": "2.1.0", "replicas": 2}
  assert result.output.splitlines() == [
    "reviews@demo revision 1: deploying 2.1.0 …",
    "follow it with: platform workload get --component reviews --environment demo",
  ]


def test_deploy_wait_follows_the_revision(api):
  api["history"] = [[revision(status="EnvironmentNotReady")], [revision(status="Succeeded", open_=False, message="2/2 replicas available")]]
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--branch", "feat/v3", "--wait")
  assert result.exit_code == 0, result.output
  assert json.loads(api["requests"][0].content) == {"branch": "feat/v3"}
  assert result.output.splitlines() == ["✓ reviews@demo revision 1: 2.1.0 running · 2/2 replicas available"]


def test_deploy_wait_fails_on_a_final_reason(api):
  api["history"] = [[revision(status="ResourcesNotSupported", open_=False, message="resources db: the platform does not provision resources yet (#263)")]]
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--version", "2.1.0", "--wait")
  assert result.exit_code == 1
  assert "reviews@demo revision 1: ResourcesNotSupported: resources db" in result.output


@pytest.mark.parametrize("args", [[], ["--version", "2.1.0", "--branch", "main"]])
def test_deploy_needs_version_or_branch(api, args):
  result = run("deploy", "--component", "reviews", "--environment", "demo", *args)
  assert result.exit_code == 1
  assert "either --version or --branch" in result.output
  assert api["requests"] == []


def test_deploy_shows_the_api_refusal(api):
  api["error"] = (403, "deploy of 'reviews': only members of its owner team (team-alpha) and platform-admins deploy it")
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--version", "2.1.0")
  assert result.exit_code == 1
  assert "403: deploy of 'reviews'" in result.output


def test_list(api):
  result = run("list", "--environment", "demo")
  assert result.exit_code == 0, result.output
  lines = result.output.splitlines()
  assert lines[0].split() == ["WORKLOAD", "VERSION", "STATUS", "REPLICAS", "REVISION", "URL"]
  assert lines[1].split() == ["reviews@demo", "2.1.0", "Available", "2/2", "1", "http://reviews.apps:80"]


def test_get(api):
  result = run("get", "--component", "reviews", "--environment", "demo")
  assert result.exit_code == 0, result.output
  assert api["requests"][0].url.path == "/v1/environments/demo/workloads/reviews"
  lines = result.output.splitlines()
  assert lines[0] == "reviews@demo (Available)"
  assert lines[4].split() == ["replicas", "2/2"]
  assert "  resource      db (postgres, provision): Ready" in lines


def test_history(api):
  result = run("history", "--environment", "demo", "--component", "reviews")
  assert result.exit_code == 0, result.output
  assert api["requests"][0].url.params["instance"] == "reviews"
  lines = result.output.splitlines()
  assert lines[0].split() == ["WORKLOAD", "REVISION", "ACTION", "VERSION", "STATUS", "BY", "CREATED"]
  assert lines[1].split() == ["reviews@demo", "1", "deploy", "2.1.0", "Succeeded", "dev@example.com", "2026-10-11T12:00:00Z"]


def test_rollback_defaults_to_the_previous_success(api):
  # Running: revision 3. Revision 2 failed, so the previous success is 1.
  api["history"] = [[
    revision(1, status="Succeeded", open_=False), revision(2, status="RolloutFailed", open_=False), revision(3, status="Succeeded", open_=False),
  ]]
  api["created"] = revision(4, action="rollback", version="1.0.0")
  api["instance"] = dict(INSTANCE, revision=3)
  result = run("rollback", "--component", "reviews", "--environment", "demo")
  assert result.exit_code == 0, result.output
  post = next(request for request in api["requests"] if request.method == "POST")
  assert json.loads(post.content) == {"rollbackTo": 1}
  assert result.output.splitlines()[0] == "reviews@demo revision 4: rolling back to revision 1 (1.0.0) …"


def test_rollback_to_a_given_revision_and_wait(api):
  api["created"] = revision(4, action="rollback", version="1.0.0")
  api["history"] = [[revision(4, action="rollback", version="1.0.0", status="Succeeded", open_=False, message="2/2 replicas available")]]
  result = run("rollback", "--component", "reviews", "--environment", "demo", "--revision", "2", "--wait")
  assert result.exit_code == 0, result.output
  assert json.loads(api["requests"][0].content) == {"rollbackTo": 2}
  assert result.output.splitlines() == ["✓ reviews@demo revision 4: 1.0.0 running · 2/2 replicas available"]


def test_rollback_without_an_earlier_success(api):
  api["history"] = [[revision(1, status="Succeeded", open_=False)]]
  result = run("rollback", "--component", "reviews", "--environment", "demo")
  assert result.exit_code == 1
  assert "no earlier revision that succeeded" in result.output


def test_remove(api):
  result = run("remove", "--component", "reviews", "--environment", "demo")
  assert result.exit_code == 0, result.output
  assert (api["requests"][0].method, api["requests"][0].url.path) == ("DELETE", "/v1/environments/demo/workloads/reviews")
  assert result.output.splitlines() == [
    "reviews@demo revision 2: removing …",
    "follow it with: platform workload history --component reviews --environment demo",
  ]


def test_remove_wait(api):
  api["history"] = [[revision(2, action="remove", version=None, status="Succeeded", open_=False)]]
  result = run("remove", "--component", "reviews", "--environment", "demo", "--wait")
  assert result.exit_code == 0, result.output
  assert result.output.splitlines() == ["✓ reviews@demo revision 2: removed from demo"]
