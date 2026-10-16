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
  reporter.planned({"cluster": (), "keycloak realm": ()})
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
  reporter.planned({"keycloak": ()})
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
  reporter.planned({"forager-provider": (), "keycloak": ()})
  reporter.failed("forager-provider", 180, RuntimeError("rollout timed out"), True)
  reporter.failed("keycloak", 3, RuntimeError("stopped"), False)
  assert lines == ["05:12:03 ✗ forager-provider    3m00s"]


from rich.console import Console  # noqa: E402

from wasp_platform.bootstrap.reporters import LiveReporter, previous_run  # noqa: E402

STEPS = {
  "cluster": (), "build images": (), "CRDs": ("cluster",), "keycloak": ("CRDs",), "traefik": ("CRDs",),
  "import images": ("cluster", "build images"), "keycloak realm": ("keycloak",), "platform-api": ("keycloak realm", "import images"),
}


def card(previous=None, ticks=None):
  console = Console(record=True, width=70, color_system=None, force_terminal=False)
  reporter = LiveReporter(console, __import__("pathlib").Path("/state/init/2026-10-14T05-12-03"), previous, "local · run 2026-10-14T05-12-03", clock=ticks or Ticks(), live=False)
  reporter.planned(STEPS)
  return console, reporter


def shown(console, reporter):
  console.print(reporter.render())
  return console.export_text()


def test_card_shows_at_most_five_steps_running_ones_first():
  ticks = Ticks()
  console, reporter = card(ticks=ticks)
  for task in ("cluster", "build images", "CRDs"):
    reporter.started(task)
    reporter.finished(task, 1)
  for task in ("keycloak", "traefik", "import images"):
    reporter.started(task)
  ticks.value = 62
  text = shown(console, reporter)
  assert "platform init" in text and "local · run 2026-10-14T05-12-03" in text
  assert "3 / 8  steps  1m02s" in text
  now_section = text.split("Now")[1].split("Overall")[0]
  for task in ("keycloak", "traefik", "import images", "keycloak realm", "platform-api"):
    assert task in now_section
  assert "waits keycloak" in now_section and "waits keycloak realm" in now_section
  assert "Now · 5 of 5" in text
  for task in ("cluster", "build images", "CRDs"):
    assert task not in now_section
  assert "■ done 3   ■ running 3   ■ waiting 2" in text
  assert "logs /state/init/2026-10-14T05-12-03" in text


def wide_card(previous=None, ticks=None):
  console = Console(record=True, width=120, color_system=None, force_terminal=False)
  reporter = LiveReporter(console, __import__("pathlib").Path("/state/init/2026-10-14T05-12-03"), previous, "local · run 2026-10-14T05-12-03", clock=ticks or Ticks(), live=False)
  reporter.planned(STEPS)
  return console, reporter


def test_card_splits_shown_steps_into_two_columns_running_first():
  ticks = Ticks()
  console, reporter = wide_card(ticks=ticks)
  for task in ("cluster", "build images", "CRDs"):
    reporter.started(task)
    reporter.finished(task, 1)
  for task in ("keycloak", "traefik", "import images"):
    reporter.started(task)
  ticks.value = 62
  text = shown(console, reporter)
  now_section = text.split("Now")[1].split("Overall")[0]
  lines = [line for line in now_section.splitlines() if line.strip()]
  running_line = next(line for line in lines if line.startswith("keycloak ") or "  keycloak " in line)
  assert "keycloak realm" in running_line, "a running step and a waiting one share a row, side by side"


def test_a_narrow_card_falls_back_to_one_column():
  console = Console(record=True, width=38, color_system=None, force_terminal=False)
  reporter = LiveReporter(console, __import__("pathlib").Path("/state/init/2026-10-14T05-12-03"), None, "local · run 2026-10-14T05-12-03", clock=Ticks(), live=False)
  reporter.planned(STEPS)
  for task in ("keycloak", "traefik"):
    reporter.started(task)
  text = shown(console, reporter)
  now_section = text.split("Now")[1].split("Overall")[0]
  lines = [line for line in now_section.splitlines() if line.strip()]
  assert not any("keycloak" in line and "traefik" in line for line in lines)


def test_card_counts_the_queue_beyond_five():
  console, reporter = card()
  text = shown(console, reporter)
  assert "Now · 5 of 8" in text
  assert "+3 more waiting" in text


def test_card_compares_with_the_last_run():
  ticks = Ticks()
  console, reporter = card(previous={"steps": {"keycloak": 40.0}, "total": 120.0}, ticks=ticks)
  reporter.started("keycloak")
  ticks.value = 60
  text = shown(console, reporter)
  assert "~50% of the last run" in text
  assert "bar = time of the last run" in text


def test_a_running_bar_fills_by_the_last_run_and_stops_short_of_full():
  ticks = Ticks()
  _, reporter = card(previous={"steps": {"keycloak": 40.0}, "total": 120.0}, ticks=ticks)
  reporter.started("keycloak")
  ticks.value = 20
  half = reporter._bar(40, "keycloak", ticks.value)
  assert [span.style for span in half.spans] == ["blue", "grey37"] and half.spans[0].end == 20
  ticks.value = 400
  late = reporter._bar(40, "keycloak", ticks.value)
  assert late.spans[0].end == 38


def test_card_at_the_end_shows_the_slowest_steps():
  ticks = Ticks()
  console, reporter = card(ticks=ticks)
  for number, task in enumerate(STEPS):
    reporter.started(task)
    reporter.finished(task, number + 1)
  ticks.value = 212
  reporter.close()
  text = shown(console, reporter)
  assert "8 / 8  steps  3m32s" in text
  slowest = text.split("Slowest")[1].split("Overall")[0]
  assert "platform-api" in slowest and "keycloak realm" in slowest and "import images" in slowest
  assert "cluster" not in slowest
  assert "of the last run" not in text


def test_card_keeps_the_failing_step():
  console, reporter = card()
  reporter.started("keycloak")
  reporter.started("traefik")
  reporter.failed("keycloak", 300, RuntimeError("rollout timed out"), True)
  reporter.failed("traefik", 2, RuntimeError("stopped"), False)
  reporter.close()
  text = shown(console, reporter)
  assert "keycloak" in text and "5m00s" in text
  assert "traefik" not in text.split("Overall")[0]
  assert "failed 1" in text


def test_previous_run_is_the_newest_that_succeeded(tmp_path):
  assert previous_run(tmp_path / "missing") is None
  for name, result, seconds in (("2026-10-13T10-00-00", "succeeded", 40.0), ("2026-10-14T10-00-00", "failed", 300.0)):
    (tmp_path / name).mkdir()
    (tmp_path / name / "run.yaml").write_text(yaml.safe_dump({"result": result, "steps": [{"step": "keycloak", "seconds": seconds}], "totalSeconds": seconds}))
  (tmp_path / "2026-10-14T11-00-00").mkdir()
  assert previous_run(tmp_path) == {"steps": {"keycloak": 40.0}, "total": 40.0}


SETTINGS = [("target", "local", "/home/you/.config/platform/init.yaml"), ("aws_profile", "—", "default")]


def test_card_opens_with_the_settings_and_their_file():
  console = Console(record=True, width=70, color_system=None, force_terminal=False)
  reporter = LiveReporter(console, __import__("pathlib").Path("/state/init/run"), None, "local · run 2026-10-14T05-12-03", SETTINGS, clock=Ticks(), live=False)
  reporter.planned(STEPS)
  text = shown(console, reporter)
  assert "settings from" in text and "/home/you/.config/platform/init.yaml" in text
  top = text.split("steps")[0]
  assert "target" in top and "init.yaml" in top and "default" in top
  assert "/home/you/.config/platform/init.yaml  " not in top.split("target")[1]


def test_notes_close_the_card_and_warnings_stand_out():
  console, reporter = card()
  reporter.note("cluster", "cluster platform-local already exists, reusing it")
  reporter.note("keycloak", "warning: GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET not set")
  text = shown(console, reporter)
  notes = text.split("Notes")[1]
  assert "cluster platform-local already exists" in notes
  assert "⚠ keycloak" in notes and "warning:" not in notes
  assert text.index("Notes") > text.index("Overall")


def test_the_settings_card_is_the_top_of_the_run_card():
  from wasp_platform.bootstrap.reporters import settings_card

  console = Console(record=True, width=70, color_system=None, force_terminal=False)
  console.print(settings_card(console, SETTINGS))
  text = console.export_text()
  assert "platform init" in text and "settings from /home/you/.config/platform/init.yaml" in text
  assert "default" in text
