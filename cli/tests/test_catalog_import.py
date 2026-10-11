import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app
from wasp_platform.commands.catalog_import import ImportFileError, read_documents

runner = CliRunner()
ACTIONS = ("create", "update", "unchanged", "skip", "forbidden", "error")
CREATE = {"kind": "Domain", "name": "messaging", "action": "create", "source": "c.yaml#2", "spec": {"owner": "team-alpha", "parent": "communication"}}
UPDATE = {"kind": "Resource", "name": "greeting-db", "action": "update", "source": "c.yaml#3", "spec": {}, "changes": {"owner": ["team-beta", "team-alpha"], "description": ["old", None]}}
SKIP = {"kind": "Group", "name": "team-alpha", "action": "skip", "source": "o.yaml#1", "reason": "identity lives in Keycloak (#186)"}
ERROR = {"kind": "System", "name": "orphan", "action": "error", "source": "x.yaml#1", "field": "spec.domain", "reason": "domain 'nowhere' not found"}
UNCHANGED = {"kind": "Domain", "name": "communication", "action": "unchanged", "source": "c.yaml#1"}


def plan(*items, applied=False):
  summary = dict.fromkeys(ACTIONS, 0)
  for item in items:
    summary[item["action"]] += 1
  return {"items": list(items), "summary": summary, "planHash": "sha256:abc", "applied": applied}


@pytest.fixture
def api(monkeypatch):
  calls = []
  responses = {"review": (200, plan(CREATE, UPDATE, SKIP)), "apply": (200, plan({**CREATE, "applied": True}, {**UPDATE, "applied": True}, SKIP, applied=True))}

  def handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/v1/catalog/import"
    body = json.loads(request.content)
    calls.append(body)
    status, payload = responses["review" if body["dryRun"] else "apply"]
    return httpx.Response(status, json=payload)

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  api.calls, api.responses = calls, responses
  return api


@pytest.fixture
def files(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  (tmp_path / "catalog" / "team").mkdir(parents=True)
  (tmp_path / "catalog" / "b.yaml").write_text("kind: Domain\nmetadata:\n  name: b\n---\n---\nkind: System\nmetadata:\n  name: s\n")
  (tmp_path / "catalog" / "team" / "a.yml").write_text("kind: Group\nmetadata:\n  name: team-alpha\n")
  (tmp_path / "catalog" / "notes.txt").write_text("ignored")
  return tmp_path


def run(*args, input=None):
  return runner.invoke(app, ["catalog", "import", *args], input=input)


def test_read_folder_recursive_sorted_and_multi_document(files):
  documents = read_documents([files / "catalog"])
  assert [document["source"] for document in documents] == ["catalog/b.yaml#1", "catalog/b.yaml#2", "catalog/team/a.yml#1"]
  assert documents[1]["document"]["kind"] == "System"


def test_same_file_twice_is_read_once(files):
  documents = read_documents([files / "catalog", files / "catalog" / "b.yaml"])
  assert len(documents) == 3


def test_dates_become_text(files):
  (files / "dated.yaml").write_text("kind: Domain\nmetadata:\n  name: d\n  annotations:\n    since: 2026-10-10\n")
  document = read_documents([files / "dated.yaml"])[0]["document"]
  assert document["metadata"]["annotations"]["since"] == "2026-10-10"
  json.dumps(document)


def test_missing_path_and_invalid_yaml(files):
  with pytest.raises(ImportFileError, match="nope.yaml: no such file or directory"):
    read_documents([files / "nope.yaml"])
  (files / "bad.yaml").write_text("kind: [unclosed\n")
  with pytest.raises(ImportFileError, match=r"bad.yaml:\d+: invalid YAML"):
    read_documents([files / "bad.yaml"])
  (files / "empty").mkdir()
  with pytest.raises(ImportFileError, match="no YAML documents found"):
    read_documents([files / "empty"])


def test_missing_path_fails_without_calling_the_api(api, files):
  result = run("nope.yaml")
  assert result.exit_code == 1
  assert "nope.yaml: no such file or directory" in result.output
  assert api.calls == []


def test_review_table(api, files):
  result = run("catalog", "--dry-run")
  assert result.exit_code == 0, result.output
  lines = result.output.splitlines()
  assert lines[0].split() == ["KIND", "NAME", "ACTION", "DETAIL"]
  assert "parent communication" in lines[1]
  assert "description: old → —; owner: team-beta → team-alpha" in lines[2]
  assert "identity lives in Keycloak (#186)" in lines[3]
  assert "1 to create, 1 to update, 0 unchanged, 1 skipped." in result.output
  assert [call["dryRun"] for call in api.calls] == [True]


def test_confirm_sends_the_reviewed_hash(api, files):
  result = run("catalog", input="y\n")
  assert result.exit_code == 0, result.output
  assert "Apply? [y/N]" in result.output
  assert "✓ 1 created, 1 updated" in result.output
  assert api.calls[1] == {"documents": api.calls[0]["documents"], "dryRun": False, "planHash": "sha256:abc"}


def test_refuse_applies_nothing(api, files):
  result = run("catalog", input="n\n")
  assert result.exit_code == 0
  assert "nothing was applied" in result.output
  assert len(api.calls) == 1


def test_yes_applies_without_hash(api, files):
  result = run("catalog", "--yes")
  assert result.exit_code == 0, result.output
  assert "Apply?" not in result.output
  assert api.calls[1]["planHash"] is None


def test_errors_stop_before_asking(api, files):
  api.responses["review"] = (200, plan(CREATE, ERROR))
  result = run("catalog", "--yes")
  assert result.exit_code == 1
  assert "spec.domain: domain 'nowhere' not found (x.yaml#1)" in result.output
  assert "fix the errors above; nothing was applied" in result.output
  assert len(api.calls) == 1


def test_nothing_to_do(api, files):
  api.responses["review"] = (200, plan(UNCHANGED, SKIP))
  result = run("catalog")
  assert result.exit_code == 0
  assert "nothing to do" in result.output
  assert len(api.calls) == 1


def test_json_without_yes_is_a_dry_run(api, files):
  result = run("catalog", "--output", "json")
  assert result.exit_code == 0
  assert json.loads(result.output)["planHash"] == "sha256:abc"
  assert len(api.calls) == 1


def test_json_with_yes_prints_the_result(api, files):
  result = run("catalog", "--output", "json", "--yes")
  assert result.exit_code == 0
  assert json.loads(result.output)["applied"] is True


def test_stale_plan_shows_the_new_plan(api, files):
  message = "catalog changed since the plan was made: review the plan again"
  api.responses["apply"] = (409, {"error": {"code": "conflict", "message": message, "plan": plan({**UPDATE, "changes": {"owner": ["team-gamma", "team-alpha"]}})}})
  result = run("catalog", input="y\n")
  assert result.exit_code == 1
  assert "owner: team-gamma → team-alpha" in result.output
  assert f"409: {message}" in result.output


def test_skip_of_a_non_entity_shows_its_source(api, files):
  api.responses["review"] = (200, plan(CREATE, {"kind": None, "name": None, "action": "skip", "source": "docs/mkdocs.yml#1", "reason": "not a Backstage entity"}))
  result = run("catalog", "--dry-run")
  assert "not a Backstage entity (docs/mkdocs.yml#1)" in result.output
