from datetime import datetime, timedelta

import yaml

from wasp_platform.bootstrap.reporters import LogReporter, PlainReporter, file_name


class Clock:
  def __init__(self):
    self.now = datetime(2026, 10, 14, 5, 12, 3)

  def __call__(self):
    return self.now


def test_file_names_are_the_start_order_and_the_step_in_kebab_case():
  assert file_name(1, "cluster") == "01-cluster.log"
  assert file_name(12, "keycloak admin permissions") == "12-keycloak-admin-permissions.log"
  assert file_name(3, "CRDs") == "03-crds.log"


def test_one_folder_per_run_one_file_per_step_and_latest(tmp_path):
  clock = Clock()
  record = LogReporter(tmp_path, {"target": {"value": "local", "source": "flag"}}, now=clock)
  assert record.folder == tmp_path / "2026-10-14T05-12-03"
  assert (tmp_path / "latest").resolve() == record.folder
  record.started("build images")
  record.started("cluster")
  record.command("cluster", ("k3d", "cluster", "list", "--output", "json"))
  record.output("cluster", "[]")
  record.exited("cluster", 0)
  record.note("cluster", "cluster platform-local already exists, reusing it")
  clock.now += timedelta(seconds=2)
  record.finished("cluster", 0.6)
  record.finished("build images", 2.0)
  record.close()

  assert sorted(path.name for path in record.folder.iterdir()) == ["01-build-images.log", "02-cluster.log", "run.yaml"]
  log = (record.folder / "02-cluster.log").read_text().splitlines()
  assert log == [
    "05:12:03 ▶ cluster",
    "05:12:03 $ k3d cluster list --output json",
    "[]",
    "05:12:03 exit 0",
    "05:12:03 · cluster platform-local already exists, reusing it",
    "05:12:05 ✓ cluster  0.6s",
  ]
  run = yaml.safe_load((record.folder / "run.yaml").read_text())
  assert run["result"] == "succeeded"
  assert run["settings"] == {"target": {"value": "local", "source": "flag"}}
  assert run["steps"] == [
    {"step": "cluster", "seconds": 0.6, "result": "done", "log": "02-cluster.log"},
    {"step": "build images", "seconds": 2.0, "result": "done", "log": "01-build-images.log"},
  ]
  assert run["totalSeconds"] == 2.0


def test_numbers_follow_the_start_order_after_earlier_steps_ended(tmp_path):
  record = LogReporter(tmp_path, {}, now=Clock())
  record.started("cluster")
  record.finished("cluster", 0.6)
  record.started("CRDs")
  assert record.file_of("CRDs").name == "02-crds.log"


def test_a_failed_run_names_the_step_and_its_error(tmp_path):
  record = LogReporter(tmp_path, {}, now=Clock())
  record.started("forager-provider")
  record.started("keycloak")
  record.failed("forager-provider", 180.0, RuntimeError("rollout timed out"), True)
  record.failed("keycloak", 3.0, RuntimeError("stopped: another step failed"), False)
  record.close(RuntimeError("rollout timed out"))
  run = yaml.safe_load((record.folder / "run.yaml").read_text())
  assert run["result"] == "failed"
  assert run["failedStep"] == "forager-provider"
  assert run["error"] == "rollout timed out"
  assert [step["result"] for step in run["steps"]] == ["failed", "stopped"]
  assert record.file_of("forager-provider").read_text().splitlines()[-2] == "rollout timed out"


def test_a_failure_outside_every_step_is_recorded(tmp_path):
  record = LogReporter(tmp_path, {}, now=Clock())
  record.close(RuntimeError("'k3d' not found in PATH"))
  run = yaml.safe_load((record.folder / "run.yaml").read_text())
  assert run["result"] == "failed" and "failedStep" not in run


def test_two_runs_in_the_same_second_get_their_own_folders(tmp_path):
  first = LogReporter(tmp_path, {}, now=Clock())
  second = LogReporter(tmp_path, {}, now=Clock())
  assert first.folder != second.folder
  assert (tmp_path / "latest").resolve() == second.folder


def test_keeps_only_the_last_runs(tmp_path):
  clock = Clock()
  folders = []
  for _ in range(4):
    folders.append(LogReporter(tmp_path, {}, now=clock, keep=2).folder)
    clock.now += timedelta(minutes=1)
  assert sorted(path.name for path in tmp_path.iterdir()) == [folders[2].name, folders[3].name, "latest"]


class Ticks:
  def __init__(self):
    self.value = 0.0

  def __call__(self):
    return self.value


def plain(lines, ticks=None):
  return PlainReporter(lines.append, now=Clock(), clock=ticks or Ticks(), heartbeat=False)


def test_plain_prints_one_line_per_step_with_the_names_aligned():
  lines = []
  reporter = plain(lines)
  reporter.planned(["cluster", "keycloak realm"])
  reporter.started("cluster")
  reporter.note("cluster", "cluster platform-local already exists, reusing it")
  reporter.output("cluster", "not shown")
  reporter.finished("cluster", 0.6)
  assert lines == [
    "05:12:03 ▶ cluster",
    "05:12:03 · cluster         cluster platform-local already exists, reusing it",
    "05:12:03 ✓ cluster            0.6s",
  ]


def test_plain_beats_every_interval_while_a_step_runs():
  lines = []
  ticks = Ticks()
  reporter = plain(lines, ticks)
  reporter.planned(["keycloak"])
  reporter.started("keycloak")
  ticks.value = 29
  reporter.tick()
  ticks.value = 30
  reporter.tick()
  ticks.value = 45
  reporter.tick()
  ticks.value = 61
  reporter.tick()
  reporter.finished("keycloak", 62)
  ticks.value = 120
  reporter.tick()
  assert lines[1:] == [
    "05:12:03 … keycloak  still running [30.0s]",
    "05:12:03 … keycloak  still running [1m01s]",
    "05:12:03 ✓ keycloak    1m02s",
  ]


def test_plain_prints_only_the_failure_that_stopped_the_run():
  lines = []
  reporter = plain(lines)
  reporter.planned(["forager-provider", "keycloak"])
  reporter.failed("forager-provider", 180, RuntimeError("rollout timed out"), True)
  reporter.failed("keycloak", 3, RuntimeError("stopped"), False)
  assert lines == ["05:12:03 ✗ forager-provider    3m00s"]
