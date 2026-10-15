import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app
from wasp_platform.commands import scm as scm_module

runner = CliRunner()
PEM = "-----BEGIN PRIVATE KEY-----\nMIIEfake\n-----END PRIVATE KEY-----\n"


class FakeApi:
  """The scm routes of the Platform API; `after_gets` scripts how the status moves while the CLI polls."""

  def __init__(self):
    self.connections = {}
    self.requests = []
    self.script = []
    self.registries = []

  def view(self, name):
    return dict(self.connections[name])

  def handler(self, request: httpx.Request) -> httpx.Response:
    self.requests.append(request)
    if request.url.path == "/v1/registries":
      return httpx.Response(200, json={"items": self.registries})
    parts = request.url.path.split("/")[4:]
    if parts == [] and request.method == "POST":
      body = json.loads(request.content)
      item = {
        "name": body["name"], "vendor": body["vendor"], "org": body["org"], "default": body["default"],
        "status": "Verifying" if body.get("appId") else "AppNotCreated", "message": None,
        "appId": body.get("appId"), "appSlug": None, "installationId": None, "permissions": {},
        "repositorySelection": None, "lastValidated": None, "verifying": bool(body.get("appId")),
      }
      self.connections[body["name"]] = item
      result = dict(item)
      if not body.get("appId"):
        result["next"] = f"http://127.0.0.1:9090/v1/scm/connections/{body['name']}/github/start?state=s"
      return httpx.Response(202, json=result)
    if parts == []:
      return httpx.Response(200, json={"items": list(self.connections.values())})
    name = parts[0]
    if name not in self.connections:
      return httpx.Response(404, json={"error": {"code": "not_found", "message": f"connection '{name}' not found"}})
    if len(parts) == 1 and request.method == "GET":
      if self.script:
        self.connections[name].update(self.script.pop(0))
      return httpx.Response(200, json=self.view(name))
    if len(parts) == 1 and request.method == "DELETE":
      slug = self.connections.pop(name)["appSlug"]
      return httpx.Response(200, json={"name": name, "deleted": True, "appSettingsUrl": f"https://github.com/organizations/acme/settings/apps/{slug}"})
    if parts[1] == "verify":
      self.connections[name]["verifying"] = True
      return httpx.Response(202, json=self.view(name))
    for item in self.connections.values():
      item["default"] = item["name"] == name
    return httpx.Response(200, json=self.view(name))


@pytest.fixture
def api(monkeypatch):
  fake = FakeApi()
  transport = httpx.MockTransport(fake.handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  monkeypatch.setattr(scm_module.time, "sleep", lambda seconds: None)
  return fake


@pytest.fixture
def browser(monkeypatch):
  opened = []
  monkeypatch.setattr(scm_module.webbrowser, "open", lambda url: opened.append(url) or True)
  return opened


def run(*args):
  return runner.invoke(app, ["scm", "connection", *args])


CREATED = {"status": "NotInstalled", "appId": 123456, "appSlug": "acme-platform", "installUrl": "https://github.com/apps/acme-platform/installations/new"}


def test_add_opens_the_browser_and_prints_the_install_link(api, browser):
  api.script = [{}, CREATED]
  result = run("add", "acme", "--vendor", "github", "--org", "acme", "--default")
  assert result.exit_code == 0, result.output
  assert browser == ["http://127.0.0.1:9090/v1/scm/connections/acme/github/start?state=s"]
  assert 'opening the browser to create the GitHub App "acme-platform"' in result.output
  assert "app created (id 123456) · private key stored by the platform" in result.output
  assert "→ install it on the org: https://github.com/apps/acme-platform/installations/new" in result.output
  assert "then run: platform scm connection verify acme --wait" in result.output
  assert json.loads(api.requests[0].content) == {"name": "acme", "vendor": "github", "org": "acme", "default": True}


def test_add_prints_the_url_when_no_browser(api, monkeypatch):
  monkeypatch.setattr(scm_module.webbrowser, "open", lambda url: False)
  api.script = [CREATED]
  result = run("add", "acme", "--org", "acme")
  assert "Open this URL to create the App:\nhttp://127.0.0.1:9090/" in result.output


def test_add_no_browser_prints_the_url_and_returns(api, browser):
  result = run("add", "acme", "--org", "acme", "--no-browser")
  assert result.exit_code == 0, result.output
  assert browser == []
  assert "http://127.0.0.1:9090/v1/scm/connections/acme/github/start?state=s" in result.output
  assert [request.method for request in api.requests] == ["POST"]


def test_add_with_an_existing_app_sends_the_key(api, browser, tmp_path):
  key = tmp_path / "key.pem"
  key.write_text(PEM)
  api.script = [{"status": "ready", "verifying": False}]
  result = run("add", "acme", "--org", "acme", "--app-id", "123456", "--private-key-file", str(key), "--wait")
  assert result.exit_code == 0, result.output
  assert browser == []
  body = json.loads(api.requests[0].content)
  assert (body["appId"], body["privateKeyPem"]) == (123456, PEM)
  assert "acme ready" in result.output
  assert "→ register its GHCR, where builds of acme repos push: platform registry add ghcr-acme --scm-connection acme --default" in result.output


def test_no_registry_hint_when_the_org_has_one(api):
  api.connections["acme"] = {**installed(), "status": "ready"}
  api.registries = [{"name": "ghcr-acme", "address": "ghcr.io/acme", "default": True}]
  result = run("verify", "acme", "--wait")
  assert result.exit_code == 0, result.output
  assert "register its GHCR" not in result.output


def test_registry_hint_without_default_flag_when_another_is_default(api):
  api.connections["acme"] = {**installed(), "status": "ready"}
  api.registries = [{"name": "ghcr-other", "address": "ghcr.io/other", "default": True}]
  assert "platform registry add ghcr-acme --scm-connection acme\n" in run("verify", "acme", "--wait").output


def test_add_needs_both_app_options(api):
  result = run("add", "acme", "--org", "acme", "--app-id", "1")
  assert result.exit_code == 1
  assert "go together" in result.output


def installed():
  return {"name": "acme", "vendor": "github", "org": "acme", "default": False, "status": "NotInstalled", "message": None, "verifying": False, "permissions": {}}


def test_verify_wait_until_ready(api):
  api.connections["acme"] = installed()
  api.script = [{"verifying": True}, {"verifying": False}, {"status": "ready"}]
  result = run("verify", "acme", "--wait")
  assert result.exit_code == 0, result.output
  assert "acme ready" in result.output


@pytest.mark.parametrize("reason", ["NotAllRepositories", "MissingPermissions"])
def test_verify_wait_stops_on_a_reason_that_needs_a_person(api, reason):
  api.connections["acme"] = installed()
  api.script = [{"status": reason, "message": "fix it on GitHub", "verifying": False}]
  result = run("verify", "acme", "--wait")
  assert result.exit_code == 1
  assert f"acme: {reason}: fix it on GitHub" in result.output


def test_list_get_default_remove(api, browser):
  api.script = [CREATED]
  run("add", "acme", "--org", "acme")
  api.connections["acme"].update(CREATED, lastValidated="2026-10-11T12:00:00Z")
  result = run("list")
  assert result.output.splitlines()[0].split() == ["NAME", "VENDOR", "ORG", "STATUS", "DEFAULT", "VALIDATED"]
  assert "acme  github  acme  NotInstalled" in result.output
  result = run("get", "acme")
  assert "install:      https://github.com/apps/acme-platform/installations/new" in result.output
  assert "acme is the default connection" in run("default", "acme").output
  result = run("remove", "acme")
  assert "connection acme removed" in result.output
  assert "https://github.com/organizations/acme/settings/apps/acme-platform" in result.output
  assert run("get", "acme").exit_code == 1


def test_get_suggests_verify_until_ready(api):
  api.connections["acme"] = {
    "name": "acme", "vendor": "github", "org": "acme", "default": True, "status": "NotInstalled", "message": None,
    "appId": 123456, "appSlug": "acme-platform", "installationId": None, "permissions": {}, "repositorySelection": None,
    "lastValidated": None, "verifying": False, "installUrl": "https://github.com/apps/acme-platform/installations/new",
  }
  assert run("get", "acme").stderr.splitlines() == ["", "next:", "", "  platform scm connection verify acme \\", "    --wait"]


def test_get_when_ready_suggests_the_registry_the_default_and_a_component(api):
  api.connections["acme"] = {
    "name": "acme", "vendor": "github", "org": "Acme", "default": False, "status": "ready", "message": None,
    "appId": 123456, "appSlug": "acme-platform", "installationId": 99, "permissions": {"contents": "write"},
    "repositorySelection": "all", "lastValidated": None, "verifying": False,
  }
  assert run("get", "acme").stderr.splitlines() == [
    "",
    "next:",
    "",
    "  platform registry add ghcr-acme \\",
    "    --scm-connection acme \\",
    "    --default",
    "",
    "  platform scm connection default acme",
    "",
    "  platform catalog component create <component> \\",
    "    --system <system> \\",
    "    --scm acme",
  ]
  api.registries = [{"name": "ghcr-acme", "address": "ghcr.io/acme", "default": True}]
  api.connections["acme"]["default"] = True
  assert run("get", "acme").stderr.splitlines() == ["", "next:", "", "  platform catalog component create <component> \\", "    --system <system>"]
  data = json.loads(run("get", "acme", "--hide-empty", "--output", "json").stdout)
  assert "lastValidated" not in data and "message" not in data and data["installationId"] == 99
