import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app
from wasp_platform.commands import build as build_module

runner = CliRunner()
COMMIT = "1a2b3c4" + "0" * 33


def condition(type_, ok=True, reason=None, message=None):
  return {"type": type_, "status": "True" if ok else "False", "reason": reason or type_, "message": message or type_}


def build(status="pending", conditions=(), commit=None, result=None, app_spec=None, errors=(), run_url=None):
  return {
    "kind": "Build", "name": "greeting-api-a1b2c3", "component": "greeting-api", "branch": "feat/greetings",
    "requestedVersion": None, "status": status, "commit": commit, "result": result, "appSpec": app_spec,
    "errors": list(errors), "runUrl": run_url, "conditions": list(conditions),
  }


RESULT = {"version": "0.3.0-greetings.1a2b3c4", "image": "ghcr.io/wasp-foundry/greeting-api", "commit": COMMIT}
APP_SPEC = {"resources": [{"name": "db", "type": "postgres"}, {"name": "dns", "type": "dns"}, {"name": "route", "type": "route"}]}
RUNNING = build(commit=COMMIT, run_url="https://github.com/wasp-foundry/greeting-api/actions/runs/1",
                conditions=[condition("Dispatched"), condition("Running"), condition("Ready", False, "Building")])
DONE = {**build("ready", commit=COMMIT, result=RESULT, app_spec=APP_SPEC, conditions=[condition("Ready", True, "Registered")]),
        "registry": "ghcr-wasp-foundry", "image": "ghcr.io/wasp-foundry/greeting-api"}


VERSIONS = [
  {"name": "greeting-api.0.3.0-greetings.1a2b3c4", "version": "0.3.0-greetings.1a2b3c4", "branch": "feat/greetings",
   "registry": "ghcr-wasp-foundry", "createdAt": "2026-10-11T17:47:40Z", "build": "greeting-api-a1b2c3"},
  {"name": "greeting-api.0.2.0", "version": "0.2.0", "branch": "main", "createdAt": "2026-10-10T10:00:00Z", "build": None},
]


@pytest.fixture
def api(monkeypatch):
  state = {"requests": [], "polls": [RUNNING, DONE], "error": None, "gone": set()}

  def handler(request: httpx.Request) -> httpx.Response:
    state["requests"].append(request)
    if state["error"]:
      return httpx.Response(state["error"][0], json={"error": {"code": "x", "message": state["error"][1]}})
    if request.method == "POST":
      return httpx.Response(202, json=build())
    if request.url.path == "/v1/versions":
      return httpx.Response(200, json={"items": VERSIONS})
    if request.url.path.removeprefix("/v1/builds/") in state["gone"]:
      return httpx.Response(404, json={"error": {"code": "NotFound", "message": f"build '{request.url.path.rsplit('/', 1)[-1]}' not found"}})
    return httpx.Response(200, json=state["polls"].pop(0) if len(state["polls"]) > 1 else state["polls"][0])

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  monkeypatch.setattr(build_module.time, "sleep", lambda seconds: None)
  return state


def run(*args):
  return runner.invoke(app, ["build", *args])


def test_create_sends_the_request(api):
  result = run("create", "--component", "greeting-api", "--branch", "feat/greetings", "--version", "1.0.0-rc.1")
  assert result.exit_code == 0, result.output
  assert json.loads(api["requests"][0].content) == {"component": "greeting-api", "branch": "feat/greetings", "version": "1.0.0-rc.1"}
  assert "platform build get greeting-api-a1b2c3" in result.output


def test_create_wait_prints_the_deck_lines(api):
  result = run("create", "--component", "greeting-api", "--branch", "feat/greetings", "--wait")
  assert result.exit_code == 0, result.output
  assert result.output.splitlines() == [
    "building from feat/greetings @ 1a2b3c4 …",
    "✓ app-spec.yaml valid · db (postgres), dns, route",
    "✓ image greeting-api:0.3.0-greetings.1a2b3c4 pushed to ghcr-wasp-foundry (ghcr.io/wasp-foundry/greeting-api)",
  ]


def test_create_sends_the_registry(api):
  result = run("create", "--component", "greeting-api", "--branch", "main", "--registry", "ghcr-wasp-foundry")
  assert result.exit_code == 0, result.output
  assert json.loads(api["requests"][0].content) == {"component": "greeting-api", "branch": "main", "registry": "ghcr-wasp-foundry"}


def test_get_names_the_registry(api):
  api["polls"] = [DONE]
  result = run("get", "greeting-api-a1b2c3")
  assert "registry      ghcr-wasp-foundry (ghcr.io/wasp-foundry/greeting-api)" in result.output


def test_workflow_outdated_stops_the_wait(api):
  api["polls"] = [build("WorkflowOutdated", conditions=[condition("Ready", False, "WorkflowOutdated", ".github/workflows/platform-build.yaml has no input 'image'")])]
  result = run("create", "--component", "greeting-api", "--branch", "main", "--wait")
  assert result.exit_code == 1
  assert "WorkflowOutdated: .github/workflows/platform-build.yaml has no input 'image'" in result.output


def test_wait_shows_the_spec_errors(api):
  api["polls"] = [build("InvalidSpec", commit=COMMIT, errors=[{"field": "resources.db.type", "reason": "'redis' is not a resource type of the platform"}],
                        conditions=[condition("Ready", False, "InvalidSpec", "app-spec.yaml at 1a2b3c4: 1 error(s)")])]
  result = run("create", "--component", "greeting-api", "--branch", "feat/greetings", "--wait")
  assert result.exit_code == 1
  assert "resources.db.type: 'redis' is not a resource type of the platform" in result.output
  assert "InvalidSpec: app-spec.yaml at 1a2b3c4: 1 error(s)" in result.output


def test_wait_shows_the_run_of_a_failed_build(api):
  url = "https://github.com/wasp-foundry/greeting-api/actions/runs/1"
  api["polls"] = [build("BuildFailed", commit=COMMIT, run_url=url, conditions=[condition("Ready", False, "BuildFailed", f"the run ended failure: {url}")])]
  result = run("create", "--component", "greeting-api", "--branch", "feat/greetings", "--wait")
  assert result.exit_code == 1
  assert f"BuildFailed: the run ended failure: {url}" in result.output


def test_wait_stops_at_workflow_not_found(api):
  api["polls"] = [build("WorkflowNotFound", conditions=[condition("Ready", False, "WorkflowNotFound", "no platform-build.yaml")])]
  result = run("create", "--component", "greeting-api", "--branch", "feat/greetings", "--wait")
  assert result.exit_code == 1
  assert "building from" not in result.output
  assert "WorkflowNotFound: no platform-build.yaml" in result.output


def test_api_errors_pass_through(api):
  api["error"] = (422, "build of 'nope': component not found")
  result = run("create", "--component", "nope", "--branch", "main")
  assert result.exit_code == 1
  assert "component not found" in result.output


def test_list_reads_the_version_index(api):
  result = run("list", "--component", "greeting-api")
  assert result.exit_code == 0, result.output
  assert api["requests"][0].url.path == "/v1/versions"
  assert api["requests"][0].url.params["component"] == "greeting-api"
  lines = result.output.splitlines()
  assert lines[0].split() == ["NAME", "VERSION", "BRANCH", "REGISTRY", "CREATED"]
  assert lines[1].split() == ["greeting-api.0.3.0-greetings.1a2b3c4", "0.3.0-greetings.1a2b3c4", "feat/greetings", "ghcr-wasp-foundry", "2026-10-11T17:47:40Z"]
  # Indexed before #365: no registry recorded.
  assert lines[2].split() == ["greeting-api.0.2.0", "0.2.0", "main", "—", "2026-10-10T10:00:00Z"]


def test_get_shows_the_steps(api):
  api["polls"] = [RUNNING]
  result = run("get", "greeting-api-a1b2c3")
  assert result.exit_code == 0, result.output
  assert "build/greeting-api-a1b2c3 (pending)" in result.output
  assert "commit        1a2b3c4" in result.output
  assert "✓ Running" in result.output


def test_get_takes_the_name_of_a_version(api):
  api["gone"] = {"greeting-api.0.3.0-greetings.1a2b3c4"}
  api["polls"] = [DONE]
  result = run("get", "greeting-api.0.3.0-greetings.1a2b3c4")
  assert result.exit_code == 0, result.output
  assert [request.url.path for request in api["requests"]] == [
    "/v1/builds/greeting-api.0.3.0-greetings.1a2b3c4", "/v1/versions", "/v1/builds/greeting-api-a1b2c3",
  ]
  assert "build/greeting-api-a1b2c3 (ready)" in result.output


def test_get_of_a_version_whose_build_is_gone(api):
  api["gone"] = {"greeting-api.0.3.0-greetings.1a2b3c4", "greeting-api-a1b2c3"}
  result = run("get", "greeting-api.0.3.0-greetings.1a2b3c4")
  assert result.exit_code == 1
  assert "version greeting-api.0.3.0-greetings.1a2b3c4: its build greeting-api-a1b2c3 is gone (builds are kept for 24 h after they end)" in result.output


def test_get_of_a_version_without_a_build(api):
  api["gone"] = {"greeting-api.0.2.0"}
  result = run("get", "greeting-api.0.2.0")
  assert result.exit_code == 1
  assert "version greeting-api.0.2.0 was registered without a build" in result.output


def test_get_of_an_unknown_name(api):
  api["gone"] = {"nope"}
  result = run("get", "nope")
  assert result.exit_code == 1
  assert "build 'nope' not found" in result.output
