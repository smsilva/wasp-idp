import threading
import time

import pytest

from wasp_platform.bootstrap.tasks import Task, run_tasks
from wasp_platform.bootstrap.timings import Timings


def test_each_task_gets_the_results_of_what_it_needs():
  tasks = [
    Task("cluster", lambda results: "k3d"),
    Task("build", lambda results: "image:1"),
    Task("import", lambda results: f"{results['build']} into {results['cluster']}", needs=("cluster", "build")),
  ]
  results = run_tasks(tasks, lambda message: None, Timings())
  assert results["import"] == "image:1 into k3d"


def test_independent_tasks_run_at_the_same_time():
  barrier = threading.Barrier(3, timeout=2)
  tasks = [Task(name, lambda results: barrier.wait()) for name in ("keycloak", "traefik", "build")]
  run_tasks(tasks, lambda message: None, Timings())


def test_a_task_starts_only_after_what_it_needs():
  order = []
  tasks = [
    Task("api", lambda results: order.append("api"), needs=("keycloak",)),
    Task("keycloak", lambda results: (time.sleep(0.05), order.append("keycloak"))),
  ]
  run_tasks(tasks, lambda message: None, Timings())
  assert order == ["keycloak", "api"]


def test_prints_one_whole_line_when_each_task_starts_and_ends():
  lines = []
  timings = Timings()
  run_tasks([Task("CRDs", lambda results: None)], lines.append, timings)
  assert lines[0] == "▶ CRDs"
  assert lines[1].startswith("✓ CRDs") and lines[1].endswith("s")
  assert [name for name, _ in timings.steps] == ["CRDs"]


def test_the_first_failure_stops_the_rest_and_is_the_one_raised():
  stopped = threading.Event()
  started = []

  def fail(results):
    raise RuntimeError("rollout timed out")

  def slow(results):
    stopped.wait(2)
    raise RuntimeError("cancelled")

  tasks = [
    Task("forager", fail),
    Task("keycloak", slow),
    Task("api", lambda results: started.append("api"), needs=("keycloak",)),
  ]
  lines = []
  with pytest.raises(RuntimeError, match="rollout timed out"):
    run_tasks(tasks, lines.append, Timings(), on_failure=stopped.set)
  assert started == []
  assert any(line.startswith("✗ forager") for line in lines)
  assert not any(line.startswith("✗ keycloak") for line in lines)


def test_an_unknown_dependency_is_a_programming_error():
  with pytest.raises(ValueError, match="needs unknown task 'nope'"):
    run_tasks([Task("api", lambda results: None, needs=("nope",))], lambda message: None, Timings())
