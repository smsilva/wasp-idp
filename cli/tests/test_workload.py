import json

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app

runner = CliRunner()
COMMIT = "1a2b3c4" + "0" * 33
# As the kube API returns it: sorted keys.
APP_SPEC = {"apiVersion": "score.dev/v1b1", "containers": {"api": {"image": "."}}, "metadata": {"name": "greeting-api"}, "x-extra": 1}
SPEC = {
  "kind": "WorkloadSpec", "component": "greeting-api", "version": "0.3.0-greetings.1a2b3c4", "commit": COMMIT,
  "branch": "feat/greetings", "image": "ghcr.io/wasp-foundry/greeting-api", "digest": "sha256:" + "b" * 64,
  "createdAt": "2026-10-11T17:47:40Z", "appSpec": APP_SPEC,
}
VALID = {"valid": True, "errors": [], "resources": [{"name": "db", "type": "postgres"}, {"name": "dns", "type": "dns"}]}
INVALID = {"valid": False, "errors": [{"field": "resources.db.type", "reason": "'redis' is not a resource type of the platform"}], "resources": []}


@pytest.fixture
def api(monkeypatch):
  state = {"requests": [], "validation": VALID, "error": None}

  def handler(request: httpx.Request) -> httpx.Response:
    state["requests"].append(request)
    if state["error"]:
      return httpx.Response(state["error"][0], json={"error": {"code": "x", "message": state["error"][1]}})
    if request.method == "POST":
      return httpx.Response(200, json=state["validation"])
    return httpx.Response(200, json=SPEC)

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  return state


def run(*args):
  return runner.invoke(app, ["workload", "spec", *args])


def test_validate_sends_the_file(api, tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  (tmp_path / "app-spec.yaml").write_text("apiVersion: score.dev/v1b1\n")
  result = run("validate")
  assert result.exit_code == 0, result.output
  assert api["requests"][0].url.path == "/v1/workload-specs:validate"
  assert json.loads(api["requests"][0].content) == {"content": "apiVersion: score.dev/v1b1\n"}
  assert result.output.splitlines() == ["✓ app-spec.yaml valid · db (postgres), dns"]


def test_validate_shows_the_errors_and_fails(api, tmp_path):
  api["validation"] = INVALID
  path = tmp_path / "other.yaml"
  path.write_text("x: 1\n")
  result = run("validate", "--file", str(path))
  assert result.exit_code == 1
  assert "resources.db.type: 'redis' is not a resource type of the platform" in result.output
  assert "other.yaml: 1 error(s)" in result.output


def test_validate_json_fails_on_an_invalid_spec(api, tmp_path):
  api["validation"] = INVALID
  path = tmp_path / "app-spec.yaml"
  path.write_text("x: 1\n")
  result = run("validate", "--file", str(path), "--output", "json")
  assert result.exit_code == 1
  assert json.loads(result.stdout)["valid"] is False


def test_validate_a_missing_file(api, tmp_path):
  result = run("validate", "--file", str(tmp_path / "none.yaml"))
  assert result.exit_code == 1
  assert api["requests"] == []


def test_get_prints_the_spec_as_yaml(api):
  result = run("get", "--component", "greeting-api", "--branch", "feat/greetings")
  assert result.exit_code == 0, result.output
  request = api["requests"][0]
  assert request.url.path == "/v1/catalog/components/greeting-api/spec"
  assert dict(request.url.params) == {"branch": "feat/greetings"}
  assert result.output.splitlines()[0] == "# greeting-api 0.3.0-greetings.1a2b3c4 · feat/greetings @ 1a2b3c4"
  assert yaml.safe_load(result.output) == APP_SPEC
  # The order of a Score, then whatever else it carries.
  assert [line for line in result.output.splitlines() if line and line[0].isalpha()] == ["apiVersion: score.dev/v1b1", "metadata:", "containers:", "x-extra: 1"]


def test_get_json(api):
  result = run("get", "--component", "greeting-api", "--version", "0.3.0-greetings.1a2b3c4", "--output", "json")
  assert result.exit_code == 0, result.output
  assert dict(api["requests"][0].url.params) == {"version": "0.3.0-greetings.1a2b3c4"}
  assert json.loads(result.output) == SPEC


def test_get_refuses_version_and_branch(api):
  result = run("get", "--component", "greeting-api", "--version", "1.0.0", "--branch", "main")
  assert result.exit_code == 1
  assert api["requests"] == []


def test_get_spec_not_indexed_passes_through(api):
  api["error"] = (409, "SpecNotIndexed: greeting-api 0.9.0 was indexed before the version index kept the spec")
  result = run("get", "--component", "greeting-api", "--version", "0.9.0")
  assert result.exit_code == 1
  assert "409: SpecNotIndexed" in result.output
