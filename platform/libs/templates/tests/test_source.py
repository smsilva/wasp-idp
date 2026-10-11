"""Where a template's content comes from (a ref of a Git repo) and the values it renders with."""
import subprocess

import pytest

from wasp_templates.source import SourceError, coerce, fetch


def test_coerce_types_enum_and_required():
  schema = {"type": "object", "required": ["tier"], "properties": {"port": {"type": "integer", "default": 1}, "debug": {"type": "boolean"}, "tier": {"type": "string", "enum": ["a", "b"]}}}
  assert coerce(schema, {"tier": "a", "debug": "true"}, "t") == {"port": 1, "debug": True, "tier": "a"}
  with pytest.raises(SourceError, match="tier: 'c' is not one of a, b"):
    coerce(schema, {"tier": "c"}, "t")
  with pytest.raises(SourceError, match="tier: required"):
    coerce(schema, {}, "t")


def test_fetch_a_ref_from_a_git_repo(tmp_path):
  repo = tmp_path / "repo"
  (repo / "tpl" / "content").mkdir(parents=True)
  (repo / "tpl" / "content" / "a.txt").write_text("v1")
  # No hooks: a global commit-msg hook must not judge the test repo.
  git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null"]
  subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
  subprocess.run([*git, "add", "."], check=True)
  subprocess.run([*git, "commit", "--quiet", "--message", "v1"], check=True)
  subprocess.run([*git, "tag", "v1"], check=True)
  (repo / "tpl" / "content" / "a.txt").write_text("v2")
  subprocess.run([*git, "commit", "--quiet", "--all", "--message", "v2"], check=True)
  content = fetch({"repo": f"file://{repo}", "path": "tpl/content", "ref": "v1"}, tmp_path / "work", allow_local=True)
  assert (content / "a.txt").read_text() == "v1"
  with pytest.raises(SourceError, match="tpl/missing: not in"):
    fetch({"repo": f"file://{repo}", "path": "tpl/missing", "ref": "v1"}, tmp_path / "work2", allow_local=True)


@pytest.mark.parametrize("source,message", [
  ({"repo": "--upload-pack=touch /tmp/pwned", "path": "c", "ref": "main"}, "repo: an https URL"),
  ({"repo": "ext::sh -c touch% /tmp/pwned", "path": "c", "ref": "main"}, "repo: an https URL"),
  ({"repo": "https://github.com/x/y", "path": "c", "ref": "--output=/tmp/x"}, "ref: a tag, branch or commit"),
  ({"repo": "https://github.com/x/y", "path": "../c", "ref": "main"}, "path: a folder relative to the repo root"),
])
def test_fetch_refuses_what_the_api_would_refuse(tmp_path, source, message):
  # A Template CR written straight to the cluster skips the API validation; fetch checks again.
  with pytest.raises(SourceError, match=message):
    fetch(source, tmp_path)
  assert not (tmp_path / "repo").exists()


def test_fetch_refuses_a_content_path_through_a_symlink(tmp_path):
  repo = tmp_path / "repo-src"
  repo.mkdir()
  (repo / "tpl").symlink_to("/etc")
  git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null"]
  subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
  subprocess.run([*git, "add", "."], check=True)
  subprocess.run([*git, "commit", "--quiet", "--message", "link"], check=True)
  with pytest.raises(SourceError, match="outside the repo"):
    fetch({"repo": f"file://{repo}", "path": "tpl", "ref": "HEAD"}, tmp_path / "work", allow_local=True)
