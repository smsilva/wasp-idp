import pytest

from wasp_platform.bootstrap.timings import Timings, duration, summary


class Clock:
  def __init__(self):
    self.now = 0.0

  def __call__(self):
    return self.now


def test_steps_record_their_time_in_order():
  clock = Clock()
  timings = Timings(clock)
  with timings.step("cluster"):
    clock.now += 12.5
  with timings.step("build platform-api"):
    clock.now += 70
  assert timings.steps == [("cluster", 12.5), ("build platform-api", 70)]
  assert timings.as_dict() == {"steps": [{"step": "cluster", "seconds": 12.5}, {"step": "build platform-api", "seconds": 70.0}], "total_seconds": 82.5}


def test_a_failing_step_is_recorded_too():
  clock = Clock()
  timings = Timings(clock)
  with pytest.raises(RuntimeError), timings.step("rollout forager-provider"):
    clock.now += 180
    raise RuntimeError("timed out")
  assert timings.steps == [("rollout forager-provider", 180)]


def test_duration_reads_as_seconds_then_minutes():
  assert duration(0.42) == "0.4s"
  assert duration(59.94) == "59.9s"
  assert duration(65) == "1m05s"
  assert duration(416) == "6m56s"


def test_summary_aligns_steps_and_ends_with_the_total():
  clock = Clock()
  timings = Timings(clock)
  with timings.step("cluster"):
    clock.now += 5
  with timings.step("build platform-api"):
    clock.now += 65
  assert summary(timings) == [
    "cluster              5.0s",
    "build platform-api  1m05s",
    "total               1m10s",
  ]


def test_init_prints_the_timings_before_the_result(monkeypatch, tmp_path):
  from typer.testing import CliRunner

  from wasp_platform.bootstrap import local
  from wasp_platform.cli import app

  def install(admin_emails, log, aws_profile, with_crossplane, timings):
    with timings.step("build platform-api"):
      pass
    return {"api_url": "http://127.0.0.1:9090", "config": "config.yaml", "issuer": "http://issuer", "google": True, "cloud_account": False, "timings": timings.as_dict()}

  monkeypatch.setattr(local, "install", install)
  monkeypatch.setattr(local, "remembered", lambda: {})
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  result = CliRunner().invoke(app, ["init", "--target", "local", "--yes"])
  assert result.exit_code == 0, result.output
  lines = result.output.splitlines()
  start = lines.index("timings:")
  assert lines[start + 1].strip().startswith("build platform-api")
  assert lines[start + 2].strip().startswith("total")
  assert "Platform API at http://127.0.0.1:9090" in lines[-2]


def test_init_prints_the_timings_so_far_when_it_fails(monkeypatch, tmp_path):
  from typer.testing import CliRunner

  from wasp_platform.bootstrap import local
  from wasp_platform.cli import app

  def install(admin_emails, log, aws_profile, with_crossplane, timings):
    with timings.step("rollout forager-provider"):
      raise local.BootstrapError("rollout timed out")

  monkeypatch.setattr(local, "install", install)
  monkeypatch.setattr(local, "remembered", lambda: {})
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  result = CliRunner().invoke(app, ["init", "--target", "local", "--yes"])
  assert result.exit_code == 1
  assert "rollout forager-provider" in result.output
  assert "rollout timed out" in result.output
