import json
from datetime import datetime, timezone

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app
from wasp_platform.commands import environment
from wasp_platform.commands.environment import remaining

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
runner = CliRunner()


@pytest.mark.parametrize("expires_at,expected", [
  (None, "—"),
  ("2026-10-13T12:00:00Z", "3d"),
  ("2026-10-13T11:00:00Z", "2d 23h"),
  ("2026-10-10T12:45:00Z", "45m"),
  ("2026-10-10T13:30:00Z", "1h 30m"),
  ("2026-10-10T12:00:20Z", "<1m"),
  ("2026-10-10T11:00:00Z", "expired"),
])
def test_remaining(expires_at, expected):
  assert remaining(expires_at, NOW) == expected


@pytest.fixture
def api(monkeypatch):
  environments = {}
  calls = {"get": 0}

  def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.method == "POST" and path == "/v1/environments":
      body = json.loads(request.content)
      item = {"name": body["name"], "profile": body["profile"], "expiresAt": None, "status": "NoProviderForCapability"}
      environments[body["name"]] = item
      return httpx.Response(202, json=item)
    if request.method == "GET" and path == "/v1/environments":
      return httpx.Response(200, json={"items": list(environments.values())})
    name = path.rsplit("/", 1)[-1]
    if name not in environments:
      return httpx.Response(404, json={"detail": f"environment '{name}' not found"})
    if request.method == "GET":
      calls["get"] += 1
      if calls["get"] >= 2:
        environments[name]["status"] = "ready"
      return httpx.Response(200, json=environments[name])
    if request.method == "DELETE":
      del environments[name]
      return httpx.Response(202, json={"name": name, "status": "deleting"})
    return httpx.Response(405)

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None: original(self, "http://api.test", transport),
  )
  monkeypatch.setattr(environment.time, "sleep", lambda seconds: None)
  return environments


def test_create_without_wait_shows_no_provider(api):
  result = runner.invoke(app, ["environment", "create", "greetings-test", "--profile", "ephemeral", "--expires", "3d"])
  assert result.exit_code == 0, result.output
  assert "provisioning greetings-test (profile: ephemeral)" in result.output
  assert "NoProviderForCapability" in result.output


def test_create_wait_until_ready(api):
  result = runner.invoke(app, ["environment", "create", "greetings-test", "--profile", "ephemeral", "--wait"])
  assert result.exit_code == 0, result.output
  assert "✓ greetings-test ready" in result.output


def test_list_table_and_json(api):
  runner.invoke(app, ["environment", "create", "dev", "--profile", "shared"])
  table = runner.invoke(app, ["environment", "list"]).output.splitlines()
  assert table[0].split() == ["NAME", "PROFILE", "STATUS", "EXPIRES"]
  assert table[1].split() == ["dev", "shared", "NoProviderForCapability", "—"]
  as_json = json.loads(runner.invoke(app, ["environment", "list", "--output", "json"]).output)
  assert as_json[0]["name"] == "dev"


def test_delete_missing_fails(api):
  result = runner.invoke(app, ["environment", "delete", "nope"])
  assert result.exit_code == 1
  assert "not found" in result.output


def test_invalid_profile_is_rejected_by_cli(api):
  result = runner.invoke(app, ["environment", "create", "x", "--profile", "production"])
  assert result.exit_code == 2


def test_init_rejects_azure():
  result = runner.invoke(app, ["init", "--target", "azure"])
  assert result.exit_code == 1
  assert "not supported yet" in result.output
