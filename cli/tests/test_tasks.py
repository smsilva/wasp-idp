import threading
import time

import pytest

from wasp_platform.bootstrap.tasks import Reporter, Task, note, run_tasks
from wasp_platform.bootstrap.timings import Timings


def test_each_task_gets_the_results_of_what_it_needs():
  tasks = [
    Task("cluster", lambda results: "k3d"),
    Task("build", lambda results: "image:1"),
    Task("import", lambda results: f"{results['build']} into {results['cluster']}", needs=("cluster", "build")),
  ]
  results = run_tasks(tasks, Reporter(), Timings())
  assert results["import"] == "image:1 into k3d"


def test_independent_tasks_run_at_the_same_time():
  barrier = threading.Barrier(3, timeout=2)
  tasks = [Task(name, lambda results: barrier.wait()) for name in ("keycloak", "traefik", "build")]
  run_tasks(tasks, Reporter(), Timings())


def test_a_task_starts_only_after_what_it_needs():
  order = []
  tasks = [
    Task("api", lambda results: order.append("api"), needs=("keycloak",)),
    Task("keycloak", lambda results: (time.sleep(0.05), order.append("keycloak"))),
  ]
  run_tasks(tasks, Reporter(), Timings())
  assert order == ["keycloak", "api"]


def test_reports_when_each_task_starts_and_ends(recorder):
  timings = Timings()
  run_tasks([Task("CRDs", lambda results: None)], recorder, timings)
  assert [event[:2] for event in recorder.events] == [("planned", ["CRDs"]), ("started", "CRDs"), ("finished", "CRDs")]
  assert [name for name, _ in timings.steps] == ["CRDs"]


def test_notes_reach_the_task_whose_thread_wrote_them(recorder):
  barrier = threading.Barrier(2, timeout=2)

  def step(name):
    def run(results):
      barrier.wait()
      for number in range(20):
        note(f"{name} {number}")
    return run

  run_tasks([Task("keycloak", step("keycloak")), Task("traefik", step("traefik"))], recorder, Timings())
  for task in ("keycloak", "traefik"):
    notes = [event[2] for event in recorder.of(task) if event[0] == "note"]
    assert notes == [f"{task} {number}" for number in range(20)]


def test_a_note_outside_a_task_goes_nowhere():
  note("planned_steps calls code that notes")


def test_the_first_failure_stops_the_rest_and_is_the_one_raised(recorder):
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
  with pytest.raises(RuntimeError, match="rollout timed out"):
    run_tasks(tasks, recorder, Timings(), on_failure=stopped.set)
  assert started == []
  failed = {event[1]: event[4] for event in recorder.events if event[0] == "failed"}
  assert failed == {"forager": True, "keycloak": False}


def test_an_unknown_dependency_is_a_programming_error():
  with pytest.raises(ValueError, match="needs unknown task 'nope'"):
    run_tasks([Task("api", lambda results: None, needs=("nope",))], Reporter(), Timings())
