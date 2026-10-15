import json

import httpx
import pytest
import yaml
from rich.text import Text
from typer.testing import CliRunner

from wasp_platform import auth, client as client_module
from wasp_platform.cli import app

runner = CliRunner()


@pytest.fixture
def api(monkeypatch):
  teams = {}
  requests = []

  def error(status, code, message):
    return httpx.Response(status, json={"error": {"code": code, "message": message}})

  def handler(request: httpx.Request) -> httpx.Response:
    requests.append(request)
    parts = request.url.path.split("/")[3:]
    if parts == [] and request.method == "GET":
      return httpx.Response(200, json={"items": [{"name": name} for name in sorted(teams)]})
    if parts == [] and request.method == "POST":
      name = json.loads(request.content)["name"]
      if name in teams:
        return error(409, "conflict", f"team '{name}' already exists")
      teams[name] = []
      return httpx.Response(201, json={"name": name, "members": []})
    name = parts[0]
    if name not in teams:
      return error(404, "not_found", f"team '{name}' not found")
    if len(parts) == 1 and request.method == "GET":
      return httpx.Response(200, json={"name": name, "members": teams[name]})
    if len(parts) == 1:
      del teams[name]
      return httpx.Response(204)
    if request.method == "POST":
      email = json.loads(request.content)["email"]
      teams[name].append({"email": email, "username": email.split("@")[0]})
      return httpx.Response(201, json={"team": name, "email": email})
    teams[name] = [member for member in teams[name] if member["email"] != parts[2]]
    return httpx.Response(204)

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  return requests


def run(*args):
  return runner.invoke(app, ["team", *args])


def test_create_list_get_delete(api):
  assert "✓ team team-alpha created" in run("create", "team-alpha").output
  assert run("list").output.split() == ["NAME", "team-alpha"]
  assert "team-alpha: 0 member(s)" in run("get", "team-alpha").output
  assert "✓ team team-alpha deleted" in run("delete", "team-alpha").output
  assert run("list").output.split() == ["NAME"]


def test_member_add_and_remove(api):
  run("create", "team-alpha")
  result = run("member", "add", "team-alpha", "dev@example.com")
  assert result.exit_code == 0, result.output
  added = [request for request in api if request.method == "POST" and request.url.path.endswith("/members")]
  assert json.loads(added[-1].content) == {"email": "dev@example.com"}
  output = run("get", "team-alpha").output
  assert "1 member(s)" in output and "dev@example.com" in output
  assert run("member", "remove", "team-alpha", "dev@example.com").exit_code == 0
  assert api[-1].method == "DELETE" and api[-1].url.path.endswith("/members/dev@example.com")


def test_errors_exit_non_zero_with_api_message(api):
  run("create", "team-alpha")
  result = run("create", "team-alpha")
  assert result.exit_code == 1
  assert "409: team 'team-alpha' already exists" in result.output
  assert "404: team 'missing' not found" in run("get", "missing").output


def test_json_output(api):
  run("create", "team-alpha")
  assert json.loads(run("list", "--output", "json").output) == [{"name": "team-alpha"}]


@pytest.mark.parametrize("output", ["yaml", "yamlc"])
def test_yaml_output(api, output):
  run("create", "team-alpha")
  result = run("get", "team-alpha", "-o", output)
  assert result.exit_code == 0, result.output
  assert yaml.safe_load(Text.from_ansi(result.output).plain) == {"name": "team-alpha", "members": []}


def test_jsonc_output_is_colored_json(api):
  run("create", "team-alpha")
  result = run("list", "-o", "jsonc")
  assert "\x1b[" in result.output
  assert json.loads(Text.from_ansi(result.output).plain) == [{"name": "team-alpha"}]


@pytest.fixture
def me(monkeypatch):
  """The caller is dev@example.com; each refresh adds the teams the next me() returns."""
  state = {"teams": [], "refreshed": 0, "fail": False}

  def refresh_now():
    if state["fail"]:
      raise auth.AuthError("session expired: run 'platform login'")
    state["refreshed"] += 1
    state["teams"] = ["team-alpha"]
    return {"access_token": "renewed"}

  monkeypatch.setattr(client_module.PlatformClient, "me", lambda self: {"sub": "s", "email": "Dev@Example.com", "teams": state["teams"]})
  monkeypatch.setattr(auth, "refresh_now", refresh_now)
  return state


def test_member_add_of_yourself_renews_the_token(api, me):
  run("create", "team-alpha")
  result = run("member", "add", "team-alpha", "dev@example.com")
  assert result.exit_code == 0, result.output
  assert "✓ dev@example.com added to team-alpha · token renewed, team-alpha is in it" in result.output
  assert me["refreshed"] == 1


def test_member_add_of_someone_else_keeps_the_token(api, me):
  run("create", "team-alpha")
  result = run("member", "add", "team-alpha", "other@example.com")
  assert result.exit_code == 0, result.output
  assert result.output.strip() == "✓ other@example.com added to team-alpha"
  assert me["refreshed"] == 0


def test_member_add_of_yourself_survives_a_failed_refresh(api, me):
  me["fail"] = True
  run("create", "team-alpha")
  result = run("member", "add", "team-alpha", "dev@example.com")
  assert result.exit_code == 0, result.output
  assert "✓ dev@example.com added to team-alpha" in result.output
  assert "platform login --refresh" in result.output


def test_get_suggests_adding_a_member(api):
  run("create", "team-alpha")
  result = run("get", "team-alpha")
  assert "next:" not in result.stdout
  assert result.stderr.splitlines() == ["", "next:", "", "  platform team member add team-alpha <email>"]
  assert run("get", "team-alpha", "--output", "json").stderr == ""


def test_hide_empty_from_the_flag_or_the_config(api, tmp_path, monkeypatch):
  run("create", "team-alpha")
  run("member", "add", "team-alpha", "dev@example.com")
  assert json.loads(run("get", "team-alpha", "--hide-empty", "--output", "json").stdout) == {"name": "team-alpha", "members": [{"email": "dev@example.com", "username": "dev"}]}
  run("member", "remove", "team-alpha", "dev@example.com")
  assert json.loads(run("get", "team-alpha", "--hide-empty", "--output", "json").stdout) == {"name": "team-alpha"}
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  (tmp_path / "platform").mkdir()
  (tmp_path / "platform" / "config.yaml").write_text("hide_empty: true\n")
  assert json.loads(run("get", "team-alpha", "--output", "json").stdout) == {"name": "team-alpha"}
  assert json.loads(run("get", "team-alpha", "--show-empty", "--output", "json").stdout) == {"name": "team-alpha", "members": []}
  (tmp_path / "platform" / "config.yaml").write_text("hide_empty: sometimes\n")
  result = run("get", "team-alpha")
  assert result.exit_code == 1
  assert "hide_empty takes true or false, got 'sometimes'" in result.stderr
