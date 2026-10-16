import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wasp_platform.bootstrap import local
from wasp_platform.bootstrap.settings import default_file
from wasp_platform.cli import app
from wasp_platform.commands import init


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
  monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
  monkeypatch.setattr(local, "remembered", lambda: {})
  monkeypatch.setattr(init, "interactive", lambda: True)


@pytest.fixture
def installed(monkeypatch):
  calls = []

  def install(**kwargs):
    calls.append(kwargs)
    return {"api_url": "http://127.0.0.1:9090", "config": "config.yaml", "issuer": "issuer", "google": True, "cloud_account": False}

  monkeypatch.setattr(local, "install", install)
  return calls


@pytest.fixture
def no_install(monkeypatch):
  monkeypatch.setattr(local, "install", lambda **_: pytest.fail("install must not run"))


def run(*args, input=None):
  return CliRunner().invoke(app, ["init", *args], input=input)


def write_file(path, admin="file@example.org"):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(f"apiVersion: platform.wasp.silvios.me/v1alpha1\nkind: InitConfig\nadmins: [{admin}]\n")
  return path


@pytest.mark.parametrize("value", ["email_not_filled", "", "you@", "@example.com", "a b@example.com", "you@example.com\n"])
def test_admin_must_be_an_email(no_install, value):
  result = run("--target", "local", "--admin", value)
  assert result.exit_code == 2
  assert "not an e-mail" in result.output


def test_shows_the_settings_and_installs_once_confirmed(installed):
  result = run("--admin", "you@example.org", input="y\n")
  assert result.exit_code == 0, result.output
  assert "admin" in result.output and "you@example.org" in result.output and "flag" in result.output
  assert installed == [{"admin_emails": ["you@example.org"], "aws_profile": None, "with_crossplane": False, "reporter": installed[0]["reporter"], "timings": installed[0]["timings"]}]


def test_declined_installs_nothing(no_install):
  result = run("--admin", "you@example.org", input="n\n")
  assert result.exit_code == 1
  assert "nothing was installed" in result.output


def test_yes_skips_the_question(installed):
  result = run("--yes")
  assert result.exit_code == 0, result.output
  assert "Proceed?" not in result.output
  assert len(installed) == 1


def test_without_a_terminal_it_needs_yes(monkeypatch, no_install):
  monkeypatch.setattr(init, "interactive", lambda: False)
  result = run()
  assert result.exit_code == 1
  assert "--yes" in result.output


def test_data_output_needs_yes(no_install):
  result = run("--output", "json")
  assert result.exit_code == 1
  assert "--yes" in result.output


def test_reads_the_default_file_when_present(installed):
  path = write_file(default_file())
  result = run("--yes")
  assert result.exit_code == 0, result.output
  assert installed[0]["admin_emails"] == ["file@example.org"]
  assert str(path) in result.output


def test_file_option_reads_only_that_file(installed, tmp_path):
  write_file(default_file(), admin="default@example.org")
  write_file(tmp_path / "other.yaml", admin="other@example.org")
  result = run("--yes", "--file", str(tmp_path / "other.yaml"))
  assert result.exit_code == 0, result.output
  assert installed[0]["admin_emails"] == ["other@example.org"]


def test_flag_wins_over_the_file(installed):
  write_file(default_file())
  result = run("--yes", "--admin", "flag@example.org")
  assert installed[0]["admin_emails"] == ["flag@example.org"]


def test_invalid_file_stops_before_any_step(no_install):
  write_file(default_file(), admin="email_not_filled")
  result = run("--yes")
  assert result.exit_code == 1
  assert "not an e-mail" in result.output


def test_missing_file_option_fails(no_install, tmp_path):
  result = run("--yes", "--file", str(tmp_path / "missing.yaml"))
  assert result.exit_code == 1
  assert "not found" in result.output


def test_generate_file_writes_the_default_file_and_installs_nothing(no_install):
  result = run("--generate-file", "--admin", "you@example.org")
  assert result.exit_code == 0, result.output
  text = default_file().read_text()
  assert "- you@example.org" in text
  assert "awsProfile" not in text and "withCrossplane" not in text
  assert str(default_file()) in result.output


def test_generate_file_to_a_path(no_install, tmp_path):
  path = tmp_path / "team.yaml"
  result = run("--generate-file", "--file", str(path))
  assert result.exit_code == 0, result.output
  assert "kind: InitConfig" in path.read_text()


def test_generate_file_keeps_an_existing_file_without_force(no_install):
  write_file(default_file())
  result = run("--generate-file", "--admin", "new@example.org")
  assert result.exit_code == 1
  assert "--force" in result.output
  assert "file@example.org" in default_file().read_text()


def test_generate_file_force_overwrites_and_keeps_what_the_flags_do_not_change(no_install):
  write_file(default_file())
  result = run("--generate-file", "--force", "--aws-profile", "dev")
  assert result.exit_code == 0, result.output
  text = default_file().read_text()
  assert "- file@example.org" in text and "awsProfile: dev" in text


def test_dry_run_lists_settings_and_steps_and_installs_nothing(no_install, monkeypatch):
  monkeypatch.setattr(local, "aws_credential_stored", lambda: False)
  result = run("--dry-run", "--admin", "you@example.org")
  assert result.exit_code == 0, result.output
  assert "you@example.org" in result.output
  assert "keycloak realm" in result.output and "platform-api" in result.output
  steps = result.output.split("steps:")[1].split()
  assert "aws-account-provider" not in steps and "crossplane" not in steps
  assert "Proceed?" not in result.output


def test_dry_run_includes_the_conditional_steps_when_enabled(no_install, monkeypatch):
  monkeypatch.setattr(local, "aws_credential_stored", lambda: False)
  result = run("--dry-run", "--output", "json", "--aws-profile", "dev", "--with-crossplane")
  assert result.exit_code == 0, result.output
  data = __import__("json").loads(result.output)
  assert data["settings"]["aws_profile"] == {"value": "dev", "source": "flag"}
  assert "aws-account-provider" in data["steps"] and "crossplane" in data["steps"]


def test_admin_can_be_repeated(installed):
  result = run("--yes", "--admin", "one@example.org", "--admin", "two@example.org")
  assert result.exit_code == 0, result.output
  assert installed[0]["admin_emails"] == ["one@example.org", "two@example.org"]
  assert "one@example.org, two@example.org" in result.output


def test_each_run_leaves_its_logs_and_prints_where(installed, tmp_path):
  result = run("--yes")
  assert result.exit_code == 0, result.output
  latest = tmp_path / "state" / "platform" / "init" / "latest"
  assert f"logs in {latest.resolve()}" in result.output
  assert "result: succeeded" in (latest / "run.yaml").read_text()


def test_a_failure_shows_the_end_of_the_failing_step_log(monkeypatch, tmp_path):
  def install(reporter, **_):
    reporter.planned({"keycloak": ()})
    reporter.started("keycloak")
    for number in range(40):
      reporter.output("keycloak", f"line {number}")
    error = local.BootstrapError("rollout timed out")
    reporter.failed("keycloak", 300, error, True)
    raise error

  monkeypatch.setattr(local, "install", install)
  result = run("--yes", "--progress", "plain")
  assert result.exit_code == 1
  assert "✗ keycloak" in result.output
  assert "last lines of" in result.output and "01-keycloak.log" in result.output
  assert "line 39" in result.output and "line 5\n" not in result.output
  assert "rollout timed out" in result.output
  assert "result: failed" in (tmp_path / "state" / "platform" / "init" / "latest" / "run.yaml").read_text()


def test_data_output_prints_nothing_while_running_and_keeps_the_logs(installed):
  result = run("--yes", "--output", "json")
  assert result.exit_code == 0, result.output
  assert __import__("json").loads(result.output)["logs"].endswith(tuple("0123456789"))


class Editor(list):
  """The commands the editor ran with; each run appends the next of `edits` to the file, as a person would."""

  def __init__(self):
    super().__init__()
    self.edits = []

  def __call__(self, command, check):
    self.append(command)
    path = Path(command[-1])
    if self.edits:
      path.write_text(path.read_text() + self.edits.pop(0))
    return subprocess.CompletedProcess(command, 0)


@pytest.fixture
def editor(monkeypatch):
  calls = Editor()
  monkeypatch.setattr(init.subprocess, "run", calls)
  for name in ("PLATFORM_EDITOR", "VISUAL", "EDITOR"):
    monkeypatch.delenv(name, raising=False)
  monkeypatch.setattr(init.shutil, "which", lambda name: None)
  return calls


@pytest.mark.parametrize(("env", "which", "expected"), [
  ({"PLATFORM_EDITOR": "nano -w", "VISUAL": "vim", "EDITOR": "emacs"}, "/usr/bin/code", ["nano", "-w"]),
  ({"VISUAL": "vim", "EDITOR": "emacs"}, "/usr/bin/code", ["vim"]),
  ({"EDITOR": "emacs -nw"}, "/usr/bin/code", ["emacs", "-nw"]),
  ({}, "/usr/bin/code", ["code", "--wait"]),
  ({}, None, ["vi"]),
])
def test_editor_order(monkeypatch, env, which, expected):
  for name in ("PLATFORM_EDITOR", "VISUAL", "EDITOR"):
    monkeypatch.delenv(name, raising=False)
  for name, value in env.items():
    monkeypatch.setenv(name, value)
  monkeypatch.setattr(init.shutil, "which", lambda name: which if name == "code" else None)
  assert init.editor_command() == expected


def test_edit_opens_the_default_file_and_installs_nothing(no_install, editor):
  write_file(default_file())
  editor.edits.append("awsProfile: dev\n")
  result = run("--edit")
  assert result.exit_code == 0, result.output
  assert editor == [["vi", str(default_file())]]
  assert "awsProfile: dev" in default_file().read_text()
  assert f"settings saved in {default_file()}" in result.output


def test_edit_writes_a_missing_file_first(no_install, editor):
  result = run("--edit", "--admin", "you@example.org")
  assert result.exit_code == 0, result.output
  assert "- you@example.org" in default_file().read_text()


def test_edit_opens_the_file_option(no_install, editor, tmp_path):
  path = write_file(tmp_path / "team.yaml")
  result = run("--edit", "--file", str(path))
  assert result.exit_code == 0, result.output
  assert editor == [["vi", str(path)]]


def test_edit_reports_an_invalid_file_and_keeps_it(no_install, editor):
  write_file(default_file())
  editor.edits.append("colour: blue\n")
  result = run("--edit")
  assert result.exit_code == 1
  assert "unknown key(s) colour" in result.output
  assert "colour: blue" in default_file().read_text()


@pytest.mark.parametrize("other", [["--dry-run"], ["--yes"], ["--generate-file"], ["--output", "json"]])
def test_edit_refuses_other_modes(no_install, editor, other):
  result = run("--edit", *other)
  assert result.exit_code == 1
  assert "--edit" in result.output
  assert editor == []


def test_edit_without_a_terminal_needs_an_editor_variable(monkeypatch, no_install, editor):
  monkeypatch.setattr(init, "interactive", lambda: False)
  result = run("--edit")
  assert result.exit_code == 1
  assert "PLATFORM_EDITOR" in result.output
  monkeypatch.setenv("PLATFORM_EDITOR", "true")
  result = run("--edit")
  assert result.exit_code == 0, result.output


def test_init_refuses_without_helm(monkeypatch):
  real_which = shutil.which
  monkeypatch.setattr(local.shutil, "which", lambda name: None if name == "helm" else real_which(name))
  result = run("--admin", "you@example.org", input="y\n")
  assert result.exit_code != 0
  assert "helm" in result.output
