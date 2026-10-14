"""Runs the steps of `platform init` by their dependencies, side by side (#444).

Each step reports what it does as events (#458): the reporter turns them into terminal lines and into
one log file per step. The step a thread works for lives in a ContextVar, so the commands and notes of
local.py reach the right step without passing it around. The first failure stops the others
(on_failure kills what is running) and is the only one reported as the cause."""
import contextvars
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable

from .timings import Timings


@dataclass(frozen=True)
class Task:
  name: str
  run: Callable[[dict[str, Any]], Any]
  needs: tuple[str, ...] = ()


class Reporter:
  """Receives the events of a run; every method may be called from any step's thread. Does nothing."""

  def planned(self, names: list[str]) -> None: ...
  def started(self, task: str) -> None: ...
  def command(self, task: str, argv: tuple[str, ...]) -> None: ...
  def output(self, task: str, line: str) -> None: ...
  def exited(self, task: str, code: int) -> None: ...
  def note(self, task: str, message: str) -> None: ...
  def finished(self, task: str, seconds: float) -> None: ...
  def failed(self, task: str, seconds: float, error: BaseException, first: bool) -> None: ...
  def close(self) -> None: ...


class Reporters(Reporter):
  """Sends every event to each reporter, in order."""

  def __init__(self, *reporters: Reporter):
    self.reporters = reporters

  def _each(self, event: str, *args) -> None:
    for reporter in self.reporters:
      getattr(reporter, event)(*args)

  def planned(self, names): self._each("planned", names)
  def started(self, task): self._each("started", task)
  def command(self, task, argv): self._each("command", task, argv)
  def output(self, task, line): self._each("output", task, line)
  def exited(self, task, code): self._each("exited", task, code)
  def note(self, task, message): self._each("note", task, message)
  def finished(self, task, seconds): self._each("finished", task, seconds)
  def failed(self, task, seconds, error, first): self._each("failed", task, seconds, error, first)
  def close(self): self._each("close")


_current: contextvars.ContextVar[tuple[str, Reporter] | None] = contextvars.ContextVar("task", default=None)


@contextmanager
def reporting(task: str, reporter: Reporter):
  """Events emitted inside belong to task. Threads started inside must copy the context to keep it."""
  token = _current.set((task, reporter))
  try:
    yield
  finally:
    _current.reset(token)


def emit(event: str, *args) -> None:
  """An event of the current step; outside a step (planned_steps, remembered) it goes nowhere."""
  current = _current.get()
  if current:
    task, reporter = current
    getattr(reporter, event)(task, *args)


def note(message: str) -> None:
  emit("note", message)


def run_tasks(tasks: list[Task], reporter: Reporter, timings: Timings, on_failure: Callable[[], None] = lambda: None) -> dict[str, Any]:
  names = {task.name for task in tasks}
  for task in tasks:
    for need in task.needs:
      if need not in names:
        raise ValueError(f"task '{task.name}' needs unknown task '{need}'")
  reporter.planned([task.name for task in tasks])
  results: dict[str, Any] = {}
  pending = list(tasks)
  running: dict[Future, Task] = {}
  failure: BaseException | None = None
  first_failure = threading.Lock()

  def execute(task: Task) -> Any:
    reporter.started(task.name)
    started = timings.clock()
    try:
      with reporting(task.name, reporter), timings.step(task.name):
        value = task.run(results)
    except BaseException as error:
      # Only the first step to fail is the cause: the others fail because on_failure stopped them, which
      # runs only after this call returns.
      reporter.failed(task.name, timings.clock() - started, error, first_failure.acquire(blocking=False))
      raise
    reporter.finished(task.name, timings.clock() - started)
    return value

  with ThreadPoolExecutor(max_workers=len(tasks) or 1) as pool:
    while pending or running:
      if failure is None:
        for task in [task for task in pending if all(need in results for need in task.needs)]:
          pending.remove(task)
          running[pool.submit(execute, task)] = task
      if not running:
        break
      done, _ = wait(running, return_when=FIRST_COMPLETED)
      for future in done:
        task = running.pop(future)
        error = future.exception()
        if error is None:
          results[task.name] = future.result()
        elif failure is None:
          failure = error
          on_failure()
  if failure is not None:
    raise failure
  return results
