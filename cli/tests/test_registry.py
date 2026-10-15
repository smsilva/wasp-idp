import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app

runner = CliRunner()

GHCR = {"kind": "OCIRegistry", "name": "ghcr-wasp-foundry", "vendor": "ghcr", "host": "ghcr.io", "namespace": "wasp-foundry",
        "address": "ghcr.io/wasp-foundry", "default": True, "pullMode": "anonymous", "status": "ready", "message": "https://ghcr.io/v2/ answered 401"}


@pytest.fixture
def api(monkeypatch):
  state = {"requests": [], "error": None}

  def handler(request: httpx.Request) -> httpx.Response:
    state["requests"].append(request)
    if state["error"]:
      return httpx.Response(state["error"][0], json={"error": {"code": "x", "message": state["error"][1]}})
    if request.method == "GET" and request.url.path == "/v1/registries":
      return httpx.Response(200, json={"items": [GHCR, {**GHCR, "name": "ghcr-smsilva", "namespace": "smsilva", "address": "ghcr.io/smsilva", "default": False, "status": "pending"}]})
    if request.method == "DELETE":
      return httpx.Response(202, json={"name": "x", "status": "deleting"})
    return httpx.Response(200, json=GHCR)

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  return state


def run(*args):
  return runner.invoke(app, ["registry", *args])


def test_add_from_the_scm_connection(api):
  result = run("add", "ghcr-wasp-foundry", "--scm-connection", "wasp-foundry", "--default")
  assert result.exit_code == 0, result.output
  assert json.loads(api["requests"][0].content) == {"name": "ghcr-wasp-foundry", "scmConnection": "wasp-foundry", "default": True}
  assert result.output.strip() == "✓ registry ghcr-wasp-foundry added (default) · ghcr.io/wasp-foundry, pushed by the CI of wasp-foundry repos"


def test_add_explicit(api):
  run("add", "ghcr-smsilva", "--vendor", "ghcr", "--namespace", "smsilva")
  assert json.loads(api["requests"][0].content) == {"name": "ghcr-smsilva", "vendor": "ghcr", "namespace": "smsilva", "default": False}


def test_list(api):
  lines = run("list").output.splitlines()
  assert lines[0].split() == ["NAME", "VENDOR", "ADDRESS", "DEFAULT", "STATUS"]
  assert lines[1].split() == ["ghcr-wasp-foundry", "ghcr", "ghcr.io/wasp-foundry", "yes", "ready"]
  assert lines[2].split() == ["ghcr-smsilva", "ghcr", "ghcr.io/smsilva", "—", "pending"]


def test_get(api):
  output = run("get", "ghcr-wasp-foundry").output
  assert output.splitlines()[0] == "ghcr-wasp-foundry: ready — https://ghcr.io/v2/ answered 401"
  assert "  address   ghcr.io/wasp-foundry" in output
  assert "  pull      anonymous" in output


def test_set_default_and_remove(api):
  assert run("set-default", "ghcr-wasp-foundry").output.strip() == "✓ ghcr-wasp-foundry is the default registry (ghcr.io/wasp-foundry)"
  assert api["requests"][-1].method == "PUT" and api["requests"][-1].url.path == "/v1/registries/ghcr-wasp-foundry/default"
  assert run("remove", "ghcr-smsilva").output.strip() == "✓ registry ghcr-smsilva removed"


def test_refusal(api):
  api["error"] = (403, "adding a registry requires group 'platform-admins'")
  result = run("add", "x", "--vendor", "ghcr", "--namespace", "acme")
  assert result.exit_code == 1
  assert "403: adding a registry requires group 'platform-admins'" in result.output


def test_get_suggests_a_build_and_set_default_when_not_the_default(api, monkeypatch):
  assert run("get", "ghcr-wasp-foundry").stderr.splitlines() == [
    "",
    "next:",
    "",
    "  platform build create \\",
    "    --component <component> \\",
    "    --branch <branch> \\",
    "    --registry ghcr-wasp-foundry",
  ]
  monkeypatch.setitem(GHCR, "default", False)
  assert "  platform registry set-default ghcr-wasp-foundry" in run("get", "ghcr-wasp-foundry").stderr.splitlines()


def test_get_hide_empty(api, monkeypatch):
  monkeypatch.setitem(GHCR, "pullMode", None)
  assert "  pull      —" in run("get", "ghcr-wasp-foundry").stdout.splitlines()
  assert "pull" not in run("get", "ghcr-wasp-foundry", "--hide-empty").stdout
  assert "pullMode" not in json.loads(run("get", "ghcr-wasp-foundry", "--hide-empty", "--output", "json").stdout)
