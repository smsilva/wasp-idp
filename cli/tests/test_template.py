"""platform catalog template: list, get, create, default, delete, import and render."""
import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app
from wasp_platform.commands import template as template_module

runner = CliRunner()
REPO = Path(__file__).parents[2]
SEED = REPO / "platform" / "templates" / "python-service"
TEMPLATE = {
  "kind": "Template", "name": "python-service", "type": "service", "default": True, "owner": "team-platform",
  "description": "FastAPI service",
  "source": {"repo": "https://github.com/smsilva/wasp-idp", "path": "platform/templates/python-service/content", "ref": "abc1234"},
  "parameters": {"type": "object", "properties": {"port": {"type": "integer", "default": 8000, "description": "Port"}}},
  "copyWithoutRendering": [".github/workflows/*"],
}
PLAN = {
  "items": [
    {"kind": "Template", "name": "python-service", "action": "create", "source": "t.yaml#1", "spec": {"source": TEMPLATE["source"]}},
    {"kind": "Step", "name": "python-service/publish", "action": "skip", "source": "t.yaml#1", "reason": "publish:github: the platform creates the repo"},
  ],
  "summary": {"create": 1, "update": 0, "unchanged": 0, "skip": 1, "forbidden": 0, "error": 0},
  "planHash": "sha256:abc", "applied": False,
}


@pytest.fixture
def api(monkeypatch):
  calls = []

  def handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content) if request.content else None
    calls.append((request.method, request.url.path, body))
    path = request.url.path
    if path == "/v1/catalog/templates" and request.method == "GET":
      return httpx.Response(200, json={"items": [TEMPLATE, {**TEMPLATE, "name": "go-service", "default": False}]})
    if path == "/v1/catalog/templates" and request.method == "POST":
      return httpx.Response(201, json={**TEMPLATE, **body})
    if path == "/v1/catalog/templates/python-service" and request.method == "GET":
      return httpx.Response(200, json=TEMPLATE)
    if path == "/v1/catalog/templates/python-service/default":
      return httpx.Response(200, json=TEMPLATE)
    if path == "/v1/catalog/templates/python-service" and request.method == "DELETE":
      return httpx.Response(409, json={"error": {"code": "conflict", "message": "template 'python-service' is the default for type 'service': make another one the default first (go-service)"}})
    if path == "/v1/catalog/templates:import":
      return httpx.Response(200, json={**PLAN, "applied": not body["dryRun"]})
    return httpx.Response(404, json={"error": {"code": "not_found", "message": path}})

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  return calls


def run(*args, input=None):
  return runner.invoke(app, ["catalog", "template", *args], input=input)


def test_list_columns(api):
  result = run("list")
  assert result.exit_code == 0, result.output
  lines = result.output.splitlines()
  assert lines[0].split() == ["NAME", "TYPE", "REF", "DEFAULT", "SOURCE"]
  assert lines[1].split() == ["python-service", "service", "abc1234", "yes", "https://github.com/smsilva/wasp-idp/platform/templates/python-service/content"]
  assert lines[2].split()[3] == "—"


def test_get_shows_parameters_with_defaults(api):
  result = run("get", "python-service")
  assert result.exit_code == 0, result.output
  assert "template/python-service" in result.output
  assert "port (integer, default 8000): Port" in result.output


def test_create_sends_the_source(api):
  result = run("create", "my-api", "--type", "service", "--owner", "team-alpha", "--repo", "https://github.com/wasp-foundry/templates", "--path", "my-api", "--ref", "v1.0.0", "--default")
  assert result.exit_code == 0, result.output
  method, path, body = api[-1]
  assert (method, path) == ("POST", "/v1/catalog/templates")
  assert body == {"name": "my-api", "type": "service", "owner": "team-alpha", "default": True, "source": {"repo": "https://github.com/wasp-foundry/templates", "path": "my-api", "ref": "v1.0.0"}}


def test_default_and_delete_conflict(api):
  assert run("default", "python-service").exit_code == 0
  assert api[-1][:2] == ("POST", "/v1/catalog/templates/python-service/default")
  result = run("delete", "python-service")
  assert result.exit_code == 1
  assert "make another one the default first (go-service)" in result.output


def test_import_shows_skipped_steps_and_asks(api, tmp_path, monkeypatch):
  monkeypatch.chdir(REPO)
  result = run("import", "idp/templates/python-service", "--repo", "https://github.com/smsilva/wasp-idp", "--ref", "main", input="y\n")
  assert result.exit_code == 0, result.output
  assert "publish:github: the platform creates the repo" in result.output
  review, apply = [call for call in api if call[1] == "/v1/catalog/templates:import"]
  assert review[2]["dryRun"] is True and apply[2]["planHash"] == "sha256:abc"
  assert review[2]["source"] == {"repo": "https://github.com/smsilva/wasp-idp", "ref": "main"}
  # Only template definitions travel, with their path from the repo root.
  assert [(document["path"], document["document"]["kind"]) for document in review[2]["documents"]] == [
    ("idp/templates/python-service/template.yaml", "Template"),
  ]


def test_import_finds_platform_format(api, monkeypatch):
  monkeypatch.chdir(REPO / "platform")
  result = run("import", "templates", "--repo", "https://github.com/smsilva/wasp-idp", "--ref", "main", "--yes")
  assert result.exit_code == 0, result.output
  documents = api[0][2]["documents"]
  assert [document["path"] for document in documents] == ["platform/templates/python-service/template.yaml"]


def test_import_without_templates_fails(api, tmp_path):
  (tmp_path / "x.yaml").write_text("kind: Domain\n")
  result = run("import", str(tmp_path), "--repo", "https://github.com/x/y", "--ref", "main")
  assert result.exit_code == 1
  assert "no templates found" in result.output


def test_render_from_local_folder(api, tmp_path):
  out = tmp_path / "demo"
  result = run("render", "--from", str(SEED), "--name", "demo", "--output", str(out), "--param", "port=9000")
  assert result.exit_code == 0, result.output
  assert "EXPOSE 9000" in (out / "Dockerfile").read_text()
  assert "platform.wasp.silvios.me/template: python-service@local" in (out / "catalog-info.yaml").read_text()
  assert api == []


def test_render_from_registry_fetches_the_registered_ref(api, tmp_path, monkeypatch):
  fetched = []

  def fake_fetch(source, into):
    fetched.append(source)
    target = into / source["path"]
    target.parent.mkdir(parents=True)
    import shutil
    shutil.copytree(SEED / "content", target)
    return target

  monkeypatch.setattr(template_module, "fetch", fake_fetch)
  out = tmp_path / "demo"
  result = run("render", "python-service", "--name", "demo", "--output", str(out))
  assert result.exit_code == 0, result.output
  assert fetched == [TEMPLATE["source"]]
  catalog = (out / "catalog-info.yaml").read_text()
  assert "name: demo" in catalog and "platform.wasp.silvios.me/template: python-service@abc1234" in catalog
  assert (out / ".github" / "workflows" / "ci.yaml").read_bytes() == (SEED / "content" / ".github" / "workflows" / "ci.yaml").read_bytes()
  assert not any("${{" in path.read_text() for path in out.rglob("*") if path.is_file() and ".github" not in path.parts)


@pytest.mark.parametrize("params,message", [
  (["port=abc"], "port: 'abc' is not an integer"),
  (["nope=1"], "nope: not a parameter of python-service (port)"),
  (["port"], "--param takes key=value, got 'port'"),
])
def test_render_rejects_bad_params(api, tmp_path, params, message):
  args = [arg for param in params for arg in ("--param", param)]
  result = run("render", "--from", str(SEED), "--name", "demo", "--output", str(tmp_path / "o"), *args)
  assert result.exit_code == 1
  assert message in result.output


def test_render_needs_a_name_or_from(api, tmp_path):
  result = run("render", "--name", "demo", "--output", str(tmp_path / "o"))
  assert result.exit_code == 1
  assert "give a template name or --from" in result.output


def test_get_suggests_render_and_create(api):
  result = run("get", "python-service")
  assert result.stderr.splitlines() == [
    "",
    "next:",
    "",
    "  platform catalog template render python-service \\",
    "    --name <component> \\",
    "    --output <folder>",
    "",
    "  platform catalog component create <component> \\",
    "    --system <system> \\",
    "    --template python-service",
  ]


def test_get_hide_empty(api, monkeypatch):
  monkeypatch.setitem(TEMPLATE, "description", None)
  monkeypatch.setitem(TEMPLATE, "parameters", {})
  lines = run("get", "python-service").stdout.splitlines()
  assert "  description  —" in lines and "  parameters   none" in lines
  lines = run("get", "python-service", "--hide-empty").stdout.splitlines()
  assert not any(line.startswith(("  description", "  parameters")) for line in lines)
  data = json.loads(run("get", "python-service", "--hide-empty", "--output", "json").stdout)
  assert "description" not in data and "parameters" not in data
