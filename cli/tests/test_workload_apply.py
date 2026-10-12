"""workload apply (#293): the plan of an environment, read from a file and diffed by the API."""
import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app
from test_workload_instance import revision

runner = CliRunner()

PLAN = """\
environment: demo
workloads:
  productpage:
    version: 1.4.0
  reviews:
    version: 2.1.0-rc.1
    replicas: 2
    resourceClasses:
      db: restored
  ratings:
    version: 1.0.2
"""


def item(instance, action, before=None, after=None, number=None):
  return {"instance": instance, "component": instance, "action": action, "from": before, "to": after, "revision": number}


def result(applied=True):
  return {
    "environment": "demo",
    "applied": applied,
    "summary": {"add": 1, "change": 1, "remove": 0, "unchanged": 1},
    "items": [
      item("productpage", "add", None, {"version": "1.4.0", "replicas": 1}, 1 if applied else None),
      item("ratings", "unchanged", {"version": "1.0.2", "replicas": 1}, {"version": "1.0.2", "replicas": 1}),
      item("reviews", "change", {"version": "2.0.0", "replicas": 1}, {"version": "2.1.0-rc.1", "replicas": 2}, 3 if applied else None),
    ],
  }


@pytest.fixture
def api(monkeypatch):
  state = {"requests": [], "error": None, "history": {
    "productpage": [{**revision(1, status="Succeeded", open_=False, message="1/1 replicas available", version="1.4.0"), "instance": "productpage"}],
    "reviews": [{**revision(3, status="Succeeded", open_=False, message="2/2 replicas available", version="2.1.0-rc.1")}],
  }}

  def handler(request: httpx.Request) -> httpx.Response:
    state["requests"].append(request)
    if state["error"]:
      return httpx.Response(state["error"][0], json={"error": {"code": "x", "message": state["error"][1]}})
    if request.method == "POST":
      return httpx.Response(200, json=result(applied=not json.loads(request.content)["dryRun"]))
    if "instance" in request.url.params:
      return httpx.Response(200, json={"items": state["history"][request.url.params["instance"]]})
    name = request.url.path.rsplit("/", 1)[-1]
    return httpx.Response(200, json={"instance": name, "url": f"http://{name}.apps:80", "resources": [{"name": "db", "type": "postgres", "mode": "compose", "status": "Ready"}] if name == "reviews" else []})

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  monkeypatch.setattr("wasp_platform.commands.workload.time.sleep", lambda seconds: None)
  return state


@pytest.fixture
def plan(tmp_path):
  path = tmp_path / "demo.yaml"
  path.write_text(PLAN)
  return path


def run(*args):
  return runner.invoke(app, ["workload", "apply", *args])


def test_dry_run_shows_the_diff(api, plan):
  outcome = run("--file", str(plan), "--dry-run")
  assert outcome.exit_code == 0, outcome.output
  request = api["requests"][0]
  assert request.url.path == "/v1/environments/demo/workloads:apply"
  assert json.loads(request.content) == {
    "workloads": {"productpage": {"version": "1.4.0"}, "reviews": {"version": "2.1.0-rc.1", "replicas": 2, "resourceClasses": {"db": "restored"}}, "ratings": {"version": "1.0.2"}},
    "dryRun": True,
    "prune": False,
  }
  lines = outcome.output.splitlines()
  assert lines[0].split() == ["WORKLOAD", "ACTION", "FROM", "TO", "REVISION"]
  assert lines[3].split() == ["reviews@demo", "change", "2.0.0", "×1", "2.1.0-rc.1", "×2", "—"]
  assert lines[-2:] == ["demo: 1 to add, 1 to change, 0 to remove", "dry run: nothing applied"]


def test_apply_writes_and_points_to_list(api, plan):
  outcome = run("--file", str(plan), "--prune")
  assert outcome.exit_code == 0, outcome.output
  assert json.loads(api["requests"][0].content)["prune"] is True
  assert "productpage@demo  add" in outcome.output
  assert outcome.output.splitlines()[-1] == "follow it with: platform workload list --environment demo"


def test_wait_follows_every_revision(api, plan):
  outcome = run("--file", str(plan), "--wait")
  assert outcome.exit_code == 0, outcome.output
  assert [request.url.params.get("instance") for request in api["requests"][1:3]] == ["productpage", "reviews"]
  assert outcome.output.splitlines()[-5:] == [
    "✓ productpage@demo revision 1: 1.4.0 running · 1/1 replicas available",
    "  url           http://productpage.apps:80",
    "✓ reviews@demo revision 3: 2.1.0-rc.1 running · 2/2 replicas available",
    "  url           http://reviews.apps:80",
    "  resource      db (postgres, compose): Ready",
  ]


def test_wait_fails_when_one_fails(api, plan):
  api["history"]["reviews"] = [revision(3, status="ResourcesNotSupported", open_=False, message="resources db (#263)")]
  outcome = run("--file", str(plan), "--wait")
  assert outcome.exit_code == 1
  assert "✓ productpage@demo revision 1" in outcome.output
  assert "reviews@demo revision 3: ResourcesNotSupported: resources db (#263)" in outcome.output
  assert "demo: 1 of 2 revision(s) did not succeed" in outcome.output


def test_json(api, plan):
  outcome = run("--file", str(plan), "--dry-run", "--output", "json")
  assert outcome.exit_code == 0, outcome.output
  assert json.loads(outcome.output)["summary"]["change"] == 1


def test_api_refusal_passes_through(api, plan):
  api["error"] = (403, "deploy of 'reviews': only members of its owner team (team-bookinfo) and platform-admins deploy it")
  outcome = run("--file", str(plan))
  assert outcome.exit_code == 1
  assert "only members of its owner team (team-bookinfo)" in outcome.output


@pytest.mark.parametrize("content,message", [
  ("workloads: {}\n", "environment is required"),
  ("environment: demo\n", "an empty plan is workloads: {}"),
  ("environment: demo\nworkloads:\n", "an empty plan is workloads: {}"),
  ("environment: demo\nworkloads:\n  reviews: 2.1.0\n", "mapping of instance"),
  ("environment: demo\nworkloads: {}\nprune: true\n", "unknown key(s) prune"),
  ("- demo\n", "a plan is a mapping"),
  ("environment: [demo\n", "not YAML"),
])
def test_invalid_plan_files(api, tmp_path, content, message):
  path = tmp_path / "plan.yaml"
  path.write_text(content)
  outcome = run("--file", str(path))
  assert outcome.exit_code == 1
  assert message in outcome.output
  assert api["requests"] == []


def test_missing_file(api, tmp_path):
  outcome = run("--file", str(tmp_path / "nope.yaml"))
  assert outcome.exit_code == 1
  assert "cannot read" in outcome.output
