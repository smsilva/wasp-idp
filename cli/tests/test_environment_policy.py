"""platform environment policy (#305)."""
import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app

runner = CliRunner()
DEFAULT = [{"type": "postgres", "mode": "provision"}]
COMPOSE = {"type": "postgres", "mode": "compose", "params": {"instance": "shared-pg"}}


@pytest.fixture
def api(monkeypatch):
  policies = {}

  def handler(request: httpx.Request) -> httpx.Response:
    name = request.url.path.split("/")[3]
    if name == "ghost":
      return httpx.Response(404, json={"error": {"code": "not_found", "message": "environment 'ghost' not found"}})
    if request.method == "PUT":
      policies[name] = json.loads(request.content)["provisioners"]
    return httpx.Response(200, json={"kind": "BindingPolicy", "environment": name, "provisioners": policies.get(name, []), "default": DEFAULT})

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  return policies


def test_set_from_a_file_and_get_both_layers(api, tmp_path):
  path = tmp_path / "policy.yaml"
  path.write_text("provisioners:\n  - type: postgres\n    mode: compose\n    params:\n      instance: shared-pg\n")
  result = runner.invoke(app, ["environment", "policy", "set", "demo", "--file", str(path)])
  assert result.exit_code == 0, result.output
  assert api["demo"] == [COMPOSE]
  assert "✓ demo: policy set" in result.output
  rows = runner.invoke(app, ["environment", "policy", "get", "demo"]).output.splitlines()
  assert rows[0].split() == ["LAYER", "TYPE", "CLASS", "ID", "MODE", "PARAMS"]
  assert rows[1].split() == ["environment", "postgres", "—", "—", "compose", "instance=shared-pg"]
  assert rows[2].split() == ["default", "postgres", "—", "—", "provision", "—"]


def test_set_from_stdin_with_an_empty_list_removes(api):
  result = runner.invoke(app, ["environment", "policy", "set", "demo", "--file", "-"], input="provisioners: []\n")
  assert result.exit_code == 0, result.output
  assert "policy removed, the platform default applies" in result.output


def test_set_refuses_a_file_without_provisioners(api, tmp_path):
  path = tmp_path / "policy.yaml"
  path.write_text("- type: postgres\n")
  result = runner.invoke(app, ["environment", "policy", "set", "demo", "--file", str(path)])
  assert result.exit_code != 0
  assert "expected a 'provisioners' list" in result.output
  assert api == {}


def test_get_json_and_errors(api):
  assert json.loads(runner.invoke(app, ["environment", "policy", "get", "demo", "--output", "json"]).output)["default"] == DEFAULT
  result = runner.invoke(app, ["environment", "policy", "get", "ghost"])
  assert result.exit_code != 0 and "environment 'ghost' not found" in result.output
