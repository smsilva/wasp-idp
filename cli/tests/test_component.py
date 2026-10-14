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
  state = {"requests": [], "polls": [DONE], "component": None, "error": None, "creating": True, "creations": []}

  def handler(request: httpx.Request) -> httpx.Response:
    state["requests"].append(request)
    path = request.url.path
    if state["error"]:
      return httpx.Response(state["error"][0], json={"error": {"code": "x", "message": state["error"][1]}})
    if request.method == "POST":
      return httpx.Response(202, json=creation())
    if request.method == "DELETE":
      return httpx.Response(204) if state["creating"] else httpx.Response(404, json={"error": {"code": "not_found", "message": "no creation of component 'greeting-api'"}})
    if path == "/v1/catalog/component-creations":
      return httpx.Response(200, json={"items": state["creations"]})
    if path.endswith("/creation"):
      if not state["creating"]:
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "creation 'greeting-api' not found"}})
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


def test_wait_on_a_stopped_creation_points_to_the_way_out(api):
  failed = creation(conditions=[condition("Ready", ok=False, reason="RepoAlreadyExists", message="left untouched")])
  api["polls"] = [failed]
  result = run("create", "greeting-api", "--system", "greeter", "--wait")
  assert result.exit_code == 1
  assert "✗ greeting-api: RepoAlreadyExists: left untouched" in result.output
  assert "rename it, request it again with --replace, or free the name with: platform catalog component creation delete greeting-api" in result.output


def test_wait_on_a_connection_reason_gives_no_replace_hint(api):
  api["polls"] = [creation(conditions=[condition("Ready", ok=False, reason="ConnectionNotReady", message="not verified")])]
  result = run("create", "greeting-api", "--system", "greeter", "--wait")
  assert result.exit_code == 1
  assert "--replace" not in result.output


def test_create_replace_sends_the_flag(api):
  result = run("create", "greeting-api", "--system", "greeter", "--replace")
  assert result.exit_code == 0, result.output
  assert json.loads(api["requests"][0].content)["replace"] is True
  run("create", "greeting-api", "--system", "greeter")
  assert "replace" not in json.loads(api["requests"][-1].content)


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


def test_get_shows_an_extra_instance_with_its_name(api):
  api["component"] = {"name": "greeting-api", "runningIn": [
    {"environment": "demo", "instance": "greeting-api", "version": "1.0.0", "status": "Available"},
    {"environment": "demo", "instance": "greeting-api-pr-1", "version": "1.1.0", "status": "Progressing"},
  ]}
  result = run("get", "greeting-api")
  assert result.exit_code == 0, result.output
  assert "running in   demo (1.0.0, Available), greeting-api-pr-1@demo (1.1.0, Progressing)" in result.stdout


INDEXED = {"name": "greeting-api", "system": "greeter", "owner": "team-alpha", "repo": "wasp-foundry/greeting-api"}


@pytest.fixture
def git(monkeypatch, tmp_path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
  calls = {"commands": [], "returncode": 0}

  def fake_run(command, **kwargs):
    calls["commands"].append(command)
    return component_module.subprocess.CompletedProcess(command, calls["returncode"])

  monkeypatch.setattr(component_module.subprocess, "run", fake_run)
  return calls


def git_protocol(tmp_path, value):
  folder = tmp_path / "config" / "platform"
  folder.mkdir(parents=True)
  (folder / "config.yaml").write_text(f"git_protocol: {value}\n")


def test_clone_uses_ssh_by_default(api, git):
  api["component"] = INDEXED
  result = run("clone", "greeting-api")
  assert result.exit_code == 0, result.output
  assert git["commands"] == [["git", "clone", "--", "git@github.com:wasp-foundry/greeting-api.git"]]
  assert "# git clone git@github.com:wasp-foundry/greeting-api.git" in result.output


def test_clone_uses_https_with_the_flag(api, git):
  api["component"] = INDEXED
  result = run("clone", "greeting-api", "--https", "--directory", "/tmp/greeting")
  assert result.exit_code == 0, result.output
  assert git["commands"] == [["git", "clone", "--", "https://github.com/wasp-foundry/greeting-api.git", "/tmp/greeting"]]


def test_clone_reads_the_protocol_from_the_config(api, git, tmp_path):
  git_protocol(tmp_path, "https")
  api["component"] = INDEXED
  result = run("clone", "greeting-api")
  assert result.exit_code == 0, result.output
  assert git["commands"][0][-1] == "https://github.com/wasp-foundry/greeting-api.git"


def test_clone_flag_wins_over_the_config(api, git, tmp_path):
  git_protocol(tmp_path, "ssh")
  api["component"] = INDEXED
  result = run("clone", "greeting-api", "--https")
  assert result.exit_code == 0, result.output
  assert git["commands"][0][-1] == "https://github.com/wasp-foundry/greeting-api.git"


def test_clone_refuses_an_unknown_protocol_in_the_config(api, git, tmp_path):
  git_protocol(tmp_path, "ftp")
  api["component"] = INDEXED
  result = run("clone", "greeting-api")
  assert result.exit_code == 1
  assert "git_protocol takes ssh or https, got 'ftp'" in result.output
  assert git["commands"] == []


def test_clone_exits_with_the_code_of_git(api, git):
  api["component"] = INDEXED
  git["returncode"] = 128
  result = run("clone", "greeting-api")
  assert result.exit_code == 128


def test_clone_refuses_a_malformed_repo(api, git):
  api["component"] = {**INDEXED, "repo": "--upload-pack=touch /tmp/x"}
  result = run("clone", "greeting-api")
  assert result.exit_code == 1
  assert "not <org>/<repo>" in result.output
  assert git["commands"] == []


def test_clone_of_an_unknown_component_suggests_list(api, git):
  api["creating"] = False
  result = run("clone", "greeting-api")
  assert result.exit_code == 1
  assert "platform catalog component list" in result.output
  assert git["commands"] == []


def test_clone_while_the_component_is_created_points_to_get(api, git):
  result = run("clone", "greeting-api")
  assert result.exit_code == 1
  assert "greeting-api is still being created: follow it with platform catalog component get greeting-api" in result.output
  assert git["commands"] == []


def test_creation_list_columns(api, monkeypatch):
  from datetime import datetime, timezone
  monkeypatch.setattr(component_module, "utcnow", lambda: datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc))
  api["creations"] = [
    {"name": "a-api", "status": "RepoAlreadyExists", "step": "RepoCreated", "requestedBy": "user-1", "createdAt": "2026-10-10T01:00:00Z", "freesAt": "2026-10-11T01:00:00Z"},
    {"name": "b-api", "status": "pending", "step": "Validated", "requestedBy": "user-1", "createdAt": "2026-10-10T02:59:30Z", "freesAt": None},
  ]
  result = run("creation", "list")
  assert result.exit_code == 0, result.output
  lines = result.stdout.splitlines()
  assert lines[0].split() == ["NAME", "STATUS", "STEP", "REQUESTED", "BY", "AGE", "FREES", "IN"]
  assert lines[1].split() == ["a-api", "RepoAlreadyExists", "RepoCreated", "user-1", "2h", "22h"]
  assert lines[2].split() == ["b-api", "pending", "Validated", "user-1", "<1m", "—"]


def test_creation_get_shows_the_steps(api):
  api["polls"] = [creation(conditions=[condition("Validated"), condition("Ready", ok=False, reason="RepoAlreadyExists", message="left untouched")])]
  result = run("creation", "get", "greeting-api")
  assert result.exit_code == 0, result.output
  assert "componentcreation/greeting-api (RepoAlreadyExists)" in result.stdout
  assert "✓ Validated" in result.stdout


def test_creation_delete_frees_the_name(api):
  result = run("creation", "delete", "greeting-api")
  assert result.exit_code == 0, result.output
  request = api["requests"][0]
  assert (request.method, request.url.path) == ("DELETE", "/v1/catalog/components/greeting-api/creation")
  assert "greeting-api is free" in result.stdout


def test_creation_delete_of_an_unknown_name_fails(api):
  api["creating"] = False
  result = run("creation", "delete", "greeting-api")
  assert result.exit_code == 1
  assert "no creation of component 'greeting-api'" in result.output
