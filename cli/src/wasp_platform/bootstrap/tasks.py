"""Runs the steps of `platform init` by their dependencies, side by side (#444).

Each task prints one whole line when it starts and one when it ends, through a lock, so parallel steps
never interleave inside a line. The first failure stops the others (on_failure kills what is running)
and is the only one reported."""
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any, Callable

from .timings import Timings, duration


@dataclass(frozen=True)
class Task:
  name: str
  run: Callable[[dict[str, Any]], Any]
  needs: tuple[str, ...] = ()


def locked(log: Callable[[str], None]) -> Callable[[str], None]:
  lock = threading.Lock()

  def say(message: str) -> None:
    with lock:
      log(message)
  return say


def run_tasks(tasks: list[Task], log: Callable[[str], None], timings: Timings, on_failure: Callable[[], None] = lambda: None) -> dict[str, Any]:
  names = {task.name for task in tasks}
  for task in tasks:
    for need in task.needs:
      if need not in names:
        raise ValueError(f"task '{task.name}' needs unknown task '{need}'")
  say = locked(log)
  results: dict[str, Any] = {}
  pending = list(tasks)
  running: dict[Future, Task] = {}
  failure: BaseException | None = None

  def execute(task: Task) -> Any:
    say(f"▶ {task.name}")
    started = timings.clock()
    try:
      with timings.step(task.name):
        value = task.run(results)
    except BaseException:
      if failure is None:
        say(f"✗ {task.name}  {duration(timings.clock() - started)}")
      raise
    say(f"✓ {task.name}  {duration(timings.clock() - started)}")
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
