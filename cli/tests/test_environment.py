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
# The api fixture's request log, for tests that check what the CLI sent.
environments_calls = {}


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
      item = {
        "name": body["name"], "profile": body["profile"], "expiresAt": None, "status": "NoProviderForCapability",
        "owner": "dev@example.com", "sharedWith": sorted(body.get("sharedWith", [])), "cloudAccount": body.get("cloudAccount"),
      }
      environments[body["name"]] = item
      return httpx.Response(202, json=item)
    if request.method == "GET" and path == "/v1/environments":
      calls["list_params"] = dict(request.url.params)
      return httpx.Response(200, json={"items": list(environments.values())})
    if "/shares/" in path:
      name, team = path.split("/")[3], path.split("/")[5]
      shared = set(environments[name]["sharedWith"])
      if request.method == "PUT":
        shared.add(team)
      elif team in shared:
        shared.discard(team)
      else:
        return httpx.Response(404, json={"error": {"code": "not_found", "message": f"environment '{name}' is not shared with '{team}'"}})
      environments[name]["sharedWith"] = sorted(shared)
      return httpx.Response(200, json=environments[name])
    name = path.rsplit("/", 1)[-1]
    if name not in environments:
      return httpx.Response(404, json={"error": {"code": "not_found", "message": f"environment '{name}' not found"}})
    if request.method == "GET":
      calls["get"] += 1
      if calls["get"] >= 2 and not environments[name].get("cloudAccount"):
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
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  monkeypatch.setattr(environment.time, "sleep", lambda seconds: None)
  environments_calls.update(calls=calls)
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
  assert table[0].split() == ["NAME", "PROFILE", "ACCOUNT", "STATUS", "EXPIRES", "OWNER", "SHARED"]
  assert table[1].split() == ["dev", "shared", "—", "NoProviderForCapability", "—", "dev@example.com", "—"]
  as_json = json.loads(runner.invoke(app, ["environment", "list", "--output", "json"]).output)
  assert as_json[0]["name"] == "dev"


def test_create_shared_with_teams(api):
  result = runner.invoke(app, ["environment", "create", "dev", "--profile", "shared", "--share-with", "team-alpha", "--share-with", "team-beta"])
  assert result.exit_code == 0, result.output
  assert api["dev"]["sharedWith"] == ["team-alpha", "team-beta"]
  assert runner.invoke(app, ["environment", "list"]).output.splitlines()[1].split()[-2:] == ["team-alpha,", "team-beta"]


def test_create_in_a_cloud_account(api):
  result = runner.invoke(app, ["environment", "create", "cloud-dev", "--profile", "ephemeral", "--cloud-account", "nonprod-aws"])
  assert result.exit_code == 0, result.output
  assert "provisioning cloud-dev (profile: ephemeral, cloud account: nonprod-aws)" in result.output
  assert api["cloud-dev"]["cloudAccount"] == "nonprod-aws"
  assert runner.invoke(app, ["environment", "list"]).output.splitlines()[1].split()[:3] == ["cloud-dev", "ephemeral", "nonprod-aws"]
  assert "in cloud account nonprod-aws" in runner.invoke(app, ["environment", "get", "cloud-dev"]).output


def test_wait_gives_up_when_no_provider_claims_it(api, monkeypatch):
  # Unclaimed after the grace: no provider is installed for it, so --wait stops instead of waiting out the timeout.
  clock = iter(range(0, 1000, 10))
  monkeypatch.setattr(environment.time, "monotonic", lambda: next(clock))
  result = runner.invoke(app, ["environment", "create", "cloud-dev", "--profile", "ephemeral", "--cloud-account", "nonprod-aws", "--wait"])
  assert result.exit_code == 1
  assert "cloud-dev: no provider claimed it" in result.output
  assert "in cloud accounts" in result.output


def test_share_and_unshare(api):
  runner.invoke(app, ["environment", "create", "dev", "--profile", "shared"])
  result = runner.invoke(app, ["environment", "share", "dev", "--team", "team-alpha"])
  assert result.exit_code == 0, result.output
  assert "✓ dev shared with team-alpha" in result.output
  assert api["dev"]["sharedWith"] == ["team-alpha"]
  assert "✓ dev no longer shared with team-alpha" in runner.invoke(app, ["environment", "unshare", "dev", "--team", "team-alpha"]).output
  result = runner.invoke(app, ["environment", "unshare", "dev", "--team", "team-alpha"])
  assert result.exit_code == 1
  assert "is not shared with 'team-alpha'" in result.output


def test_list_all_asks_the_api_for_everything(api):
  runner.invoke(app, ["environment", "list"])
  assert environments_calls["calls"]["list_params"] == {}
  runner.invoke(app, ["environment", "list", "--all"])
  assert environments_calls["calls"]["list_params"] == {"all": "true"}


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


def test_save_kubeconfig_writes_private_file(tmp_path, monkeypatch):
  import stat
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  env = environment.save_kubeconfig({"name": "vc", "status": "ready", "kubeconfigData": "apiVersion: v1\n"})
  path = tmp_path / "platform" / "environments" / "vc.kubeconfig"
  assert env["kubeconfig"] == str(path) and "kubeconfigData" not in env
  assert path.read_text() == "apiVersion: v1\n"
  assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_save_kubeconfig_without_data_changes_nothing():
  env = environment.save_kubeconfig({"name": "pending", "status": "Provisioning"})
  assert "kubeconfig" not in env


PERSONAL = """apiVersion: v1
kind: Config
clusters:
- name: vc
  cluster:
    server: https://127.0.0.1:7100
users:
- name: vc
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1
      command: platform
      args: [environment, credential, vc]
      interactiveMode: Never
"""


def test_save_kubeconfig_points_the_plugin_at_this_cli(tmp_path, monkeypatch):
  import yaml
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  installed = tmp_path / "venv" / "bin" / "platform"
  installed.parent.mkdir(parents=True)
  installed.touch()
  monkeypatch.setattr(environment.sys, "argv", [str(installed), "environment", "get", "vc"])
  env = environment.save_kubeconfig({"name": "vc", "status": "ready", "kubeconfigData": PERSONAL})
  plugin = yaml.safe_load(open(env["kubeconfig"]))["users"][0]["user"]["exec"]
  assert plugin["command"] == str(installed)
  assert plugin["args"] == ["environment", "credential", "vc"]


def test_executable_falls_back_to_path_lookup(monkeypatch):
  monkeypatch.setattr(environment.sys, "argv", ["/usr/bin/pytest"])
  assert environment.executable() == "platform"


def credential_api(monkeypatch, handler):
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", httpx.MockTransport(handler), lambda: "test-token"),
  )


def test_credential_prints_exec_credential(monkeypatch):
  def handler(request):
    assert (request.method, request.url.path) == ("POST", "/v1/environments/vc/credentials")
    return httpx.Response(200, json={"token": "sa-token", "expirationTimestamp": "2026-10-11T12:10:00Z"})

  credential_api(monkeypatch, handler)
  result = runner.invoke(app, ["environment", "credential", "vc"])
  assert result.exit_code == 0
  assert json.loads(result.stdout) == {
    "apiVersion": "client.authentication.k8s.io/v1", "kind": "ExecCredential",
    "status": {"token": "sa-token", "expirationTimestamp": "2026-10-11T12:10:00Z"},
  }


def test_credential_refused_goes_to_stderr(monkeypatch):
  credential_api(monkeypatch, lambda request: httpx.Response(403, json={"error": {"code": "forbidden", "message": "environment 'vc' is not yours nor shared with your teams"}}))
  result = runner.invoke(app, ["environment", "credential", "vc"])
  assert result.exit_code == 1
  assert result.stdout == ""
  assert "not yours nor shared" in result.stderr


def test_get_admin_writes_admin_kubeconfig(tmp_path, monkeypatch):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

  def handler(request):
    if request.url.path.endswith("/admin-kubeconfig"):
      return httpx.Response(200, json={"name": "vc", "kubeconfigData": "apiVersion: v1\nkind: Config\n"})
    return httpx.Response(200, json={"name": "vc", "status": "ready", "kubeconfigData": PERSONAL})

  credential_api(monkeypatch, handler)
  result = runner.invoke(app, ["environment", "get", "vc", "--admin"])
  assert result.exit_code == 0
  path = tmp_path / "platform" / "environments" / "vc-admin.kubeconfig"
  assert path.read_text() == "apiVersion: v1\nkind: Config\n"
  assert str(path) in result.stdout


def test_get_shows_where_the_workloads_are(tmp_path, monkeypatch):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  credential_api(monkeypatch, lambda request: httpx.Response(200, json={"name": "vc", "status": "ready", "kubeconfigData": PERSONAL, "ingress": "http://*.vc.localhost:7080"}))
  result = runner.invoke(app, ["environment", "get", "vc"])
  assert result.exit_code == 0
  assert "workloads at http://*.vc.localhost:7080" in result.stdout
