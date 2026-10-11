import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app
from wasp_platform.commands import component as component_module

runner = CliRunner()


def creation(conditions=(), repo=None, files=(), app_spec=None, default=True):
  ready = next((c for c in conditions if c["type"] == "Ready"), None)
  status = "pending" if ready is None else ("ready" if ready["status"] == "True" else ready["reason"])
  return {
    "kind": "ComponentCreation", "name": "greeting-api", "status": status,
    "template": {"name": "python-service", "ref": "abc123", "default": default},
    "repo": repo, "files": list(files), "appSpec": app_spec, "conditions": list(conditions),
  }


def condition(type_, ok=True, reason=None, message=None):
  return {"type": type_, "status": "True" if ok else "False", "reason": reason or type_, "message": message or f"{type_} done"}


DONE = creation(
  conditions=[condition(step) for step in ("Validated", "Rendered", "RepoCreated", "Pushed", "Protected", "Registered")] + [condition("Ready", reason="Created")],
  repo={"fullName": "wasp-foundry/greeting-api", "url": "https://github.com/wasp-foundry/greeting-api", "nodeId": "R_1"},
  files=["AGENTS.md", "app-spec.yaml", "catalog-info.yaml", "docs/prd.md"],
  app_spec={"containers": ["api"], "resources": ["postgres"], "routes": ["/"]},
)


@pytest.fixture
def api(monkeypatch):
  state = {"requests": [], "polls": [DONE], "component": None, "error": None}

  def handler(request: httpx.Request) -> httpx.Response:
    state["requests"].append(request)
    path = request.url.path
    if state["error"]:
      return httpx.Response(state["error"][0], json={"error": {"code": "x", "message": state["error"][1]}})
    if request.method == "POST":
      return httpx.Response(202, json=creation())
    if path.endswith("/creation"):
      return httpx.Response(200, json=state["polls"].pop(0) if len(state["polls"]) > 1 else state["polls"][0])
    if path == "/v1/catalog/components":
      items = [{"name": "greeting-api", "system": "greeter", "owner": "team-alpha", "lifecycle": "experimental", "template": "python-service@abc123"}]
      return httpx.Response(200, json={"items": items})
    if state["component"] is None:
      return httpx.Response(404, json={"error": {"code": "not_found", "message": "component 'greeting-api' not found"}})
    return httpx.Response(200, json=state["component"])

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  monkeypatch.setattr(component_module.time, "sleep", lambda seconds: None)
  return state


def run(*args, input=None):
  return runner.invoke(app, ["catalog", "component", *args], input=input)


def test_create_sends_the_request_with_params_and_prd(api, tmp_path):
  prd = tmp_path / "idea.md"
  prd.write_text("# Problem\n")
  result = run("create", "greeting-api", "--system", "greeter", "--param", "port=9000", "--prd", str(prd))
  assert result.exit_code == 0, result.output
  body = json.loads(api["requests"][0].content)
  assert body == {"name": "greeting-api", "system": "greeter", "params": {"port": "9000"}, "prd": "# Problem\n"}
  assert "creating greeting-api from template python-service@abc123" in result.output
  assert "platform catalog component get greeting-api" in result.output


def test_prd_from_stdin(api):
  result = run("create", "greeting-api", "--system", "greeter", "--prd", "-", input="from stdin\n")
  assert result.exit_code == 0, result.output
  assert json.loads(api["requests"][0].content)["prd"] == "from stdin\n"


def test_create_wait_prints_the_deck_lines(api):
  api["polls"] = [creation(conditions=[condition("Validated")]), DONE]
  result = run("create", "greeting-api", "--system", "greeter", "--wait")
  assert result.exit_code == 0, result.output
  lines = [line for line in result.stdout.splitlines() if line.startswith("✓")]
  assert lines == [
    "✓ golden path “python-service” (default for service): repo wasp-foundry/greeting-api created",
    "✓ registered in the catalog (lifecycle: experimental)",
    "✓ docs/prd.md and AGENTS.md added to the repo",
    "✓ app-spec.yaml generated: container, postgres, route /",
  ]


def test_with_template_the_first_line_has_no_default(api):
  api["polls"] = [{**DONE, "template": {**DONE["template"], "default": False}}]
  result = run("create", "greeting-api", "--system", "greeter", "--template", "python-service", "--wait")
  assert "✓ golden path “python-service”: repo wasp-foundry/greeting-api created" in result.stdout


def test_wait_stops_at_a_final_reason(api):
  failed = creation(conditions=[condition("RepoCreated", ok=False, reason="RepoAlreadyExists", message="left untouched"), condition("Ready", ok=False, reason="RepoAlreadyExists", message="left untouched")])
  api["polls"] = [failed]
  result = run("create", "greeting-api", "--system", "greeter", "--wait")
  assert result.exit_code == 1
  assert "RepoAlreadyExists" in result.output


def test_wait_shows_an_unprotected_main_as_a_warning(api):
  unprotected = condition("Protected", ok=False, reason="ProtectionUnavailable", message="main of wasp-foundry/greeting-api is not protected: Upgrade to GitHub Pro")
  api["polls"] = [{**DONE, "conditions": [unprotected if item["type"] == "Protected" else item for item in DONE["conditions"]]}]
  result = run("create", "greeting-api", "--system", "greeter", "--visibility", "private", "--wait")
  assert result.exit_code == 0, result.output
  assert "⚠ Protected: main of wasp-foundry/greeting-api is not protected" in result.output
  assert result.stdout.splitlines()[-1] == "⚠ main of wasp-foundry/greeting-api is not protected: Upgrade to GitHub Pro"


def test_wait_stops_when_github_rejects(api):
  failed = creation(conditions=[condition("Pushed", ok=False, reason="GitHubRejected", message="malformed path"), condition("Ready", ok=False, reason="GitHubRejected", message="malformed path")])
  api["polls"] = [failed]
  result = run("create", "greeting-api", "--system", "greeter", "--wait")
  assert result.exit_code == 1
  assert "GitHubRejected: malformed path" in result.output


def test_type_and_template_together_are_refused(api):
  result = run("create", "greeting-api", "--system", "greeter", "--type", "service", "--template", "python-service")
  assert result.exit_code == 1
  assert api["requests"] == []


def test_api_errors_pass_through(api):
  api["error"] = (422, "component 'greeting-api': system 'nope' not found")
  result = run("create", "greeting-api", "--system", "nope")
  assert result.exit_code == 1
  assert "system 'nope' not found" in result.output


def test_list_columns_and_filters(api):
  result = run("list", "--system", "greeter")
  assert result.exit_code == 0, result.output
  assert result.stdout.splitlines()[0].split() == ["NAME", "SYSTEM", "OWNER", "LIFECYCLE", "TEMPLATE"]
  assert "python-service@abc123" in result.stdout
  assert api["requests"][0].url.params["system"] == "greeter"


def test_get_shows_the_creation_until_the_component_is_indexed(api):
  api["polls"] = [creation(conditions=[condition("Validated"), condition("Rendered", ok=False, reason="GitHubUnavailable", message="502")])]
  result = run("get", "greeting-api")
  assert result.exit_code == 0, result.output
  assert "creating" in result.stdout
  assert "✗ Rendered" in result.stdout
  api["component"] = {"name": "greeting-api", "system": "greeter", "repo": "wasp-foundry/greeting-api"}
  result = run("get", "greeting-api")
  assert "wasp-foundry/greeting-api" in result.stdout
