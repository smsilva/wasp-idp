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
      return httpx.Response(200, json={"items": state.get("instances") or [INSTANCE]})
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
  assert json.loads(request.content) == {"component": "reviews", "version": "2.1.0", "replicas": 2}
  assert result.output.splitlines() == [
    "reviews@demo revision 1: deploying 2.1.0 …",
    "follow it with: platform workload get reviews@demo",
  ]


def test_deploy_wait_follows_the_revision(api):
  api["history"] = [[revision(status="EnvironmentNotReady")], [revision(status="Succeeded", open_=False, message="2/2 replicas available")]]
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--branch", "feat/v3", "--wait")
  assert result.exit_code == 0, result.output
  assert json.loads(api["requests"][0].content) == {"component": "reviews", "branch": "feat/v3"}
  assert result.output.splitlines() == [
    "✓ reviews@demo revision 1: 2.1.0 running · 2/2 replicas available",
    "  url           http://reviews.apps:80",
    "  resource      db (postgres, provision): Ready",
  ]


def test_deploy_wait_shows_the_public_url_and_the_class(api):
  latest = {**revision(status="Succeeded", open_=False), "resourceClasses": {"db": "restored"}}
  api["instance"] = {**INSTANCE, "publicUrl": "http://reviews.demo.localhost:7080/", "latestRevision": latest, "resources": [{"name": "db", "type": "postgres", "mode": "bind", "status": "Ready"}]}
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--version", "2.1.0", "--wait")
  assert result.exit_code == 0, result.output
  assert result.output.splitlines()[1:] == [
    "  url           http://reviews.demo.localhost:7080/",
    "  resource      db (postgres, bind, class restored): Ready",
  ]


def test_deploy_wait_without_resources_or_url_prints_no_empty_lines(api):
  api["instance"] = {**INSTANCE, "url": None, "resources": []}
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--version", "2.1.0", "--wait")
  assert result.exit_code == 0, result.output
  assert result.output.splitlines() == ["✓ reviews@demo revision 1: 2.1.0 running · 2/2 replicas available"]


def test_deploy_wait_json_is_the_revision(api):
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--version", "2.1.0", "--wait", "--output", "json")
  assert result.exit_code == 0, result.output
  assert json.loads(result.output)["kind"] == "WorkloadRevision"
  assert not any(request.url.path == "/v1/environments/demo/workloads/reviews" for request in api["requests"])


def test_deploy_wait_succeeds_when_the_details_cannot_be_read(api, monkeypatch):
  def broken(self, environment, instance):
    raise client_module.ApiError("unavailable", status=503)
  monkeypatch.setattr(client_module.PlatformClient, "get_workload", broken)
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--version", "2.1.0", "--wait")
  assert result.exit_code == 0, result.output
  assert "✓ reviews@demo revision 1: 2.1.0 running" in result.output
  assert "⚠ cannot show the url and resources" in result.output


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
  assert lines[0].split() == ["WORKLOAD", "COMPONENT", "VERSION", "STATUS", "REPLICAS", "REVISION", "TRAFFIC", "URL"]
  assert lines[1].split() == ["reviews@demo", "reviews", "2.1.0", "Available", "2/2", "1", "—", "http://reviews.apps:80"]
  assert api["requests"][-1].url.path == "/v1/workloads"
  assert dict(api["requests"][-1].url.params) == {"environment": "demo"}


def test_list_across_environments(api):
  api["instances"] = [INSTANCE, {**INSTANCE, "name": "reviews@staging", "environment": "staging"}]
  result = run("list", "--component", "reviews")
  assert result.exit_code == 0, result.output
  assert dict(api["requests"][-1].url.params) == {"component": "reviews"}
  lines = result.output.splitlines()
  assert lines[0].split() == ["WORKLOAD", "ENVIRONMENT", "COMPONENT", "VERSION", "STATUS", "REPLICAS", "REVISION", "TRAFFIC", "URL"]
  assert [line.split()[:2] for line in lines[1:]] == [["reviews@demo", "demo"], ["reviews@staging", "staging"]]


def test_get(api):
  result = run("get", "reviews", "--environment", "demo")
  assert result.exit_code == 0, result.output
  assert api["requests"][-1].url.path == "/v1/environments/demo/workloads/reviews"
  lines = result.output.splitlines()
  assert lines[0] == "reviews@demo (Available)"
  assert lines[4].split() == ["replicas", "2/2"]
  assert "  resource      db (postgres, provision): Ready" in lines


def test_history(api):
  result = run("history", "--environment", "demo", "--component", "reviews")
  assert result.exit_code == 0, result.output
  assert dict(api["requests"][0].url.params) == {"component": "reviews"}
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
  result = run("rollback", "reviews", "--environment", "demo")
  assert result.exit_code == 0, result.output
  post = next(request for request in api["requests"] if request.method == "POST")
  assert json.loads(post.content) == {"rollbackTo": 1}
  assert result.output.splitlines()[0] == "reviews@demo revision 4: rolling back to revision 1 (1.0.0) …"


def test_rollback_to_a_given_revision_and_wait(api):
  api["created"] = revision(4, action="rollback", version="1.0.0")
  api["history"] = [[revision(4, action="rollback", version="1.0.0", status="Succeeded", open_=False, message="2/2 replicas available")]]
  result = run("rollback", "reviews", "--environment", "demo", "--revision", "2", "--wait")
  assert result.exit_code == 0, result.output
  post = next(request for request in api["requests"] if request.method == "POST")
  assert json.loads(post.content) == {"rollbackTo": 2}
  assert result.output.splitlines()[:2] == ["✓ reviews@demo revision 4: 1.0.0 running · 2/2 replicas available", "  url           http://reviews.apps:80"]


def test_rollback_without_an_earlier_success(api):
  api["history"] = [[revision(1, status="Succeeded", open_=False)]]
  result = run("rollback", "reviews", "--environment", "demo")
  assert result.exit_code == 1
  assert "no earlier revision that succeeded" in result.output


def test_remove(api):
  result = run("remove", "reviews", "--environment", "demo")
  assert result.exit_code == 0, result.output
  assert (api["requests"][-1].method, api["requests"][-1].url.path) == ("DELETE", "/v1/environments/demo/workloads/reviews")
  assert result.output.splitlines() == [
    "reviews@demo revision 2: removing …",
    "follow it with: platform workload history --environment demo --instance reviews",
  ]


def test_remove_wait(api):
  api["history"] = [[revision(2, action="remove", version=None, status="Succeeded", open_=False)]]
  result = run("remove", "reviews", "--environment", "demo", "--wait")
  assert result.exit_code == 0, result.output
  assert result.output.splitlines() == ["✓ reviews@demo revision 2: removed from demo"]


def test_deploy_with_resource_classes(api):
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--version", "2.1.0", "--resource-class", "db=restored", "--resource-class", "cache=warm")
  assert result.exit_code == 0, result.output
  assert json.loads(api["requests"][0].content) == {"component": "reviews", "version": "2.1.0", "resourceClasses": {"db": "restored", "cache": "warm"}}


@pytest.mark.parametrize("value", ["db", "=restored", "db=", "db=a=b"])
def test_deploy_resource_class_is_name_equals_class(api, value):
  result = run("deploy", "--component", "reviews", "--environment", "demo", "--version", "2.1.0", "--resource-class", value)
  assert result.exit_code == 1
  assert "--resource-class takes <resource>=<class>" in result.output
  assert api["requests"] == []


def test_get_shows_the_resource_classes_of_the_newest_revision(api):
  latest = {**revision(status="Succeeded", open_=False), "resourceClasses": {"db": "restored"}}
  api["instance"] = {**INSTANCE, "latestRevision": latest, "resources": [{"name": "db", "type": "postgres", "mode": "bind", "status": "Ready"}]}
  lines = run("get", "reviews", "--environment", "demo").output.splitlines()
  assert "  resource      db (postgres, bind, class restored): Ready" in lines


def test_a_route_shows_the_public_url_first(api):
  api["instance"] = api["instances"] = None
  public = {**INSTANCE, "publicUrl": "http://reviews.demo.localhost:7080/"}
  api["instance"], api["instances"] = public, [public]
  assert run("list", "--environment", "demo").output.splitlines()[1].split()[-1] == "http://reviews.demo.localhost:7080/"
  lines = run("get", "reviews", "--environment", "demo").output.splitlines()
  assert "  url           http://reviews.demo.localhost:7080/" in lines
  assert "  internal url  http://reviews.apps:80" in lines


EXTRA = {**INSTANCE, "name": "reviews-pr-42@demo", "instance": "reviews-pr-42", "url": "http://reviews-pr-42.apps:80"}


def extra_revision(number=1, **fields):
  return {**revision(number, **fields), "name": f"demo.reviews-pr-42.{number}", "instance": "reviews-pr-42"}


def test_deploy_an_extra_instance(api):
  api["created"] = extra_revision()
  result = run("deploy", "--component", "reviews", "--instance", "reviews-pr-42", "--environment", "demo", "--branch", "feat/pr-42")
  assert result.exit_code == 0, result.output
  request = api["requests"][0]
  assert request.url.path == "/v1/environments/demo/workloads/reviews-pr-42/revisions"
  assert json.loads(request.content) == {"component": "reviews", "branch": "feat/pr-42"}
  assert result.output.splitlines() == [
    "reviews-pr-42@demo revision 1: deploying 2.1.0 …",
    "follow it with: platform workload get reviews-pr-42@demo",
  ]


def test_component_names_its_default_instance(api):
  result = run("get", "reviews", "--environment", "demo")
  assert result.exit_code == 0, result.output
  assert [request.url.path for request in api["requests"]] == ["/v1/environments/demo/workloads/reviews"]


def test_instance_at_environment(api):
  api["instance"] = EXTRA
  result = run("get", "reviews-pr-42@demo")
  assert result.exit_code == 0, result.output
  # Straight to it: no list round to resolve a component.
  assert [request.url.path for request in api["requests"]] == ["/v1/environments/demo/workloads/reviews-pr-42"]
  assert result.output.splitlines()[0] == "reviews-pr-42@demo (Available)"


def test_instance_at_the_same_environment_as_the_option(api):
  assert run("get", "reviews@demo", "--environment", "demo").exit_code == 0


@pytest.mark.parametrize("args, message", [
  ([], "give the instance"),
  (["reviews"], "give --environment, or the instance as reviews@<environment>"),
  (["reviews@staging", "--environment", "demo"], "'reviews@staging' names environment staging, --environment names demo"),
  (["reviews@"], "'reviews@' is not <instance>@<environment>"),
  (["@demo"], "'@demo' is not <instance>@<environment>"),
  (["reviews@demo", "--instance", "reviews"], "give the instance"),
])
@pytest.mark.parametrize("command", ["get", "signals", "rollback", "remove"])
def test_instance_refusals(api, command, args, message):
  result = run(command, *args)
  assert result.exit_code == 1
  assert message in result.output
  assert api["requests"] == []


@pytest.mark.parametrize("option, value", [("--component", "reviews"), ("--instance", "reviews-pr-42")])
@pytest.mark.parametrize("command", ["get", "signals", "rollback", "remove"])
def test_deprecated_options_still_work_with_a_warning(api, command, option, value):
  api["history"] = [[revision(1, status="Succeeded", open_=False)]]
  if command == "signals":
    api["instance"] = SIGNALS
  result = run(command, option, value, "--environment", "demo", *(["--revision", "1"] if command == "rollback" else []))
  assert result.exit_code == 0, result.output
  assert f"⚠ {option} is deprecated" in result.output
  assert any(f"/workloads/{value}" in request.url.path for request in api["requests"])


def test_deprecated_options_are_hidden(api):
  result = run("get", "--help")
  assert "--environment" in result.output
  assert "--component" not in result.output and "--instance" not in result.output


def test_remove_an_extra_instance(api):
  result = run("remove", "reviews-pr-42@demo")
  assert result.exit_code == 0, result.output
  assert (api["requests"][0].method, api["requests"][0].url.path) == ("DELETE", "/v1/environments/demo/workloads/reviews-pr-42")


def test_history_of_an_instance(api):
  api["history"] = [[extra_revision(status="Succeeded", open_=False)]]
  result = run("history", "--environment", "demo", "--instance", "reviews-pr-42")
  assert result.exit_code == 0, result.output
  assert dict(api["requests"][0].url.params) == {"instance": "reviews-pr-42"}
  assert result.output.splitlines()[1].split()[0] == "reviews-pr-42@demo"


SIGNALS = {
  "kind": "WorkloadSignals", "name": "reviews@demo", "environment": "demo", "instance": "reviews", "window": "5m",
  "latencyP95Ms": 42.31, "trafficRps": 3.0, "errorRate": 0.022, "saturation": {"value": 0.12, "cpu": 0.004, "memory": 0.12, "reason": None}, "message": None,
}


def test_signals(api):
  api["instance"] = SIGNALS
  result = run("signals", "reviews", "--environment", "demo")
  assert result.exit_code == 0, result.output
  request = api["requests"][-1]
  assert (request.url.path, dict(request.url.params)) == ("/v1/environments/demo/workloads/reviews/signals", {"window": "5m"})
  assert result.output.splitlines() == ["latency p95 42.31 ms · traffic 3 req/s · errors 2.2% · saturation 12%"]


def test_signals_without_requests_nor_limit(api):
  api["instance"] = {
    **SIGNALS, "latencyP95Ms": None, "trafficRps": 0.0, "errorRate": None, "message": "no requests in window",
    "saturation": {"value": None, "cpu": None, "memory": None, "reason": "no CPU or memory limit declared"},
  }
  result = run("signals", "reviews", "--environment", "demo", "--window", "1h")
  assert result.exit_code == 0, result.output
  assert dict(api["requests"][-1].url.params) == {"window": "1h"}
  assert result.output.splitlines() == [
    "latency p95 — · traffic 0 req/s · errors — · saturation — (no CPU or memory limit declared)",
    "  no requests in window (5m)",
  ]


def test_signals_json(api):
  api["instance"] = SIGNALS
  result = run("signals", "reviews", "--environment", "demo", "--output", "json")
  assert json.loads(result.output) == SIGNALS


def test_signals_without_prometheus(api):
  api["error"] = (503, "capability 'observability' has no provider installed: see platform status observability")
  result = run("signals", "reviews", "--environment", "demo")
  assert result.exit_code == 1
  assert "observability" in result.output
