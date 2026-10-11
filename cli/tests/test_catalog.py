import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app

runner = CliRunner()
KINDS = {"domains": "Domain", "systems": "System", "resources": "Resource"}
PARENTS = {"domains": "parent", "systems": "domain", "resources": "system"}


@pytest.fixture
def api(monkeypatch):
  store = {plural: {} for plural in KINDS}
  requests = []

  def handler(request: httpx.Request) -> httpx.Response:
    requests.append(request)
    parts = request.url.path.split("/")[3:]
    if parts == ["entities"]:
      kind = request.url.params.get("kind")
      items = [
        {**entity, "parent": entity.get(PARENTS[plural])}
        for plural in store for entity in store[plural].values()
        if kind is None or KINDS[plural].lower() == kind
      ]
      return httpx.Response(200, json={"items": items})
    plural = parts[0]
    if request.method == "POST":
      body = json.loads(request.content)
      if body["name"] in store[plural]:
        return httpx.Response(409, json={"error": {"code": "conflict", "message": f"{KINDS[plural].lower()} '{body['name']}' already exists"}})
      store[plural][body["name"]] = {"kind": KINDS[plural], "description": None, **body}
      return httpx.Response(201, json=store[plural][body["name"]])
    if len(parts) == 1:
      return httpx.Response(200, json={"items": list(store[plural].values())})
    name = parts[1]
    if name not in store[plural]:
      return httpx.Response(404, json={"error": {"code": "not_found", "message": f"{KINDS[plural].lower()} '{name}' not found"}})
    if request.method == "GET":
      return httpx.Response(200, json={**store[plural][name], "dependents": []})
    del store[plural][name]
    return httpx.Response(204)

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  return requests


def run(*args):
  return runner.invoke(app, ["catalog", *args])


def test_create_domain_sends_only_given_fields(api):
  result = run("domain", "create", "communication", "--owner", "team-alpha")
  assert result.exit_code == 0, result.output
  assert "✓ domain communication created" in result.output
  assert json.loads(api[-1].content) == {"name": "communication", "owner": "team-alpha"}


def test_create_subdomain_system_and_resource(api):
  run("domain", "create", "messaging", "--parent", "communication", "--owner", "team-alpha")
  assert json.loads(api[-1].content)["parent"] == "communication"
  run("system", "create", "greeter", "--domain", "messaging", "--owner", "team-alpha", "--description", "Greetings")
  assert json.loads(api[-1].content) == {"name": "greeter", "owner": "team-alpha", "domain": "messaging", "description": "Greetings"}
  result = run("resource", "create", "greeting-db", "--type", "database", "--system", "greeter", "--owner", "team-alpha")
  assert "✓ resource greeting-db created" in result.output


def test_required_options_are_enforced_by_cli(api):
  assert run("system", "create", "greeter", "--owner", "team-alpha").exit_code == 2
  assert run("resource", "create", "greeting-db", "--system", "greeter", "--owner", "team-alpha").exit_code == 2


def test_catalog_list_table_and_json(api):
  run("domain", "create", "communication", "--owner", "team-alpha")
  run("system", "create", "greeter", "--domain", "communication", "--owner", "team-alpha")
  lines = run("list").output.splitlines()
  assert lines[0].split() == ["KIND", "NAME", "PARENT", "OWNER"]
  assert lines[1].split() == ["Domain", "communication", "—", "team-alpha"]
  assert lines[2].split() == ["System", "greeter", "communication", "team-alpha"]
  run("list", "--kind", "system")
  assert api[-1].url.params["kind"] == "system"
  assert [item["name"] for item in json.loads(run("list", "--output", "json").output)] == ["communication", "greeter"]


def test_kind_list_columns(api):
  run("resource", "create", "greeting-db", "--type", "database", "--system", "greeter", "--owner", "team-alpha")
  lines = run("resource", "list").output.splitlines()
  assert lines[0].split() == ["NAME", "TYPE", "SYSTEM", "OWNER"]
  assert lines[1].split() == ["greeting-db", "database", "greeter", "team-alpha"]


def test_get_shows_fields_and_dependents(api):
  run("system", "create", "greeter", "--domain", "messaging", "--owner", "team-alpha")
  output = run("system", "get", "greeter").output
  assert output.splitlines()[0] == "system/greeter"
  assert "domain" in output and "messaging" in output
  assert "dependents   none" in output


def test_delete_prints_success(api):
  run("domain", "create", "communication", "--owner", "team-alpha")
  result = run("domain", "delete", "communication")
  assert result.exit_code == 0, result.output
  assert "✓ domain communication deleted" in result.output


def test_api_errors_pass_through(api):
  result = run("system", "delete", "nope")
  assert result.exit_code == 1
  assert "404: system 'nope' not found" in result.output
  run("domain", "create", "communication", "--owner", "team-alpha")
  result = run("domain", "create", "communication", "--owner", "team-alpha")
  assert result.exit_code == 1
  assert "already exists" in result.output
