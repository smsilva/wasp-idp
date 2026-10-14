"""Where the events of `platform init` go (#458): a log folder per run, and the terminal.

LogReporter always runs: one plain-text file per step and a run.yaml, under
$XDG_STATE_HOME/platform/init/<timestamp>/, with `latest` pointing at the newest run. PlainReporter
prints one line per step, and a heartbeat while a step runs, so a long rollout never looks hung."""
import os
import re
import shlex
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

import yaml

from .tasks import Reporter
from .timings import duration

KEEP_RUNS = 20
HEARTBEAT_SECONDS = 30


def file_name(number: int, task: str) -> str:
  return f"{number:02d}-{re.sub(r'[^a-z0-9]+', '-', task.lower()).strip('-')}.log"


class LogReporter(Reporter):
  def __init__(self, base: Path, settings: dict, now: Callable[[], datetime] = datetime.now, keep: int = KEEP_RUNS):
    self.now = now
    self.base = base
    self.settings = settings
    self.started_at = now()
    stamp = self.started_at.strftime("%Y-%m-%dT%H-%M-%S")
    base.mkdir(parents=True, exist_ok=True)
    self.folder = base / stamp
    suffix = 1
    while self.folder.exists():
      suffix += 1
      self.folder = base / f"{stamp}-{suffix}"
    self.folder.mkdir()
    self._point_latest()
    self._prune(keep)
    self.lock = threading.Lock()
    self.files: dict[str, TextIO] = {}
    self.paths: dict[str, Path] = {}
    self.steps: list[dict] = []
    self.failed_step: str | None = None
    self.error: str | None = None

  def _point_latest(self) -> None:
    """Replaced in one rename, so `latest` never points nowhere while the next run starts."""
    link = self.base / "latest"
    staging = self.base / f".latest-{os.getpid()}"
    staging.unlink(missing_ok=True)
    staging.symlink_to(self.folder.name)
    os.replace(staging, link)

  def _prune(self, keep: int) -> None:
    runs = sorted(path for path in self.base.iterdir() if path.is_dir() and not path.is_symlink() and not path.name.startswith("."))
    for old in runs[:-keep]:
      shutil.rmtree(old, ignore_errors=True)

  def _write(self, task: str, text: str) -> None:
    with self.lock:
      handle = self.files.get(task)
      if handle:
        handle.write(text + "\n")
        handle.flush()

  def _stamp(self) -> str:
    return self.now().strftime("%H:%M:%S")

  def file_of(self, task: str) -> Path | None:
    return self.paths.get(task)

  def started(self, task: str) -> None:
    with self.lock:
      path = self.folder / file_name(len(self.paths) + 1, task)
      self.paths[task] = path
      self.files[task] = path.open("w", encoding="utf-8")
    self._write(task, f"{self._stamp()} ▶ {task}")

  def command(self, task: str, argv: tuple[str, ...]) -> None:
    self._write(task, f"{self._stamp()} $ {shlex.join(argv)}")

  def output(self, task: str, line: str) -> None:
    self._write(task, line)

  def exited(self, task: str, code: int) -> None:
    self._write(task, f"{self._stamp()} exit {code}")

  def note(self, task: str, message: str) -> None:
    self._write(task, f"{self._stamp()} · {message}")

  def finished(self, task: str, seconds: float) -> None:
    self._end(task, f"✓ {task}  {duration(seconds)}", {"step": task, "seconds": round(seconds, 1), "result": "done"})

  def failed(self, task: str, seconds: float, error: BaseException, first: bool) -> None:
    if first:
      self.failed_step, self.error = task, str(error) or type(error).__name__
    result = "failed" if first else "stopped"
    self._write(task, str(error))
    self._end(task, f"✗ {task}  {duration(seconds)}", {"step": task, "seconds": round(seconds, 1), "result": result})

  def _end(self, task: str, line: str, record: dict) -> None:
    self._write(task, f"{self._stamp()} {line}")
    with self.lock:
      self.steps.append({**record, "log": self.paths[task].name})
      self.files.pop(task).close()

  def close(self, error: BaseException | None = None) -> None:
    """error: a failure outside every step (a missing tool), when no step failed."""
    if error is not None and self.error is None:
      self.error = str(error) or type(error).__name__
    with self.lock:
      for handle in self.files.values():
        handle.close()
      self.files.clear()
    record = {
      "startedAt": self.started_at.isoformat(timespec="seconds"),
      "result": "failed" if self.error else "succeeded",
      **({"failedStep": self.failed_step} if self.failed_step else {}),
      **({"error": self.error} if self.error else {}),
      "settings": self.settings,
      "steps": self.steps,
      "totalSeconds": round((self.now() - self.started_at).total_seconds(), 1),
    }
    (self.folder / "run.yaml").write_text(yaml.safe_dump(record, sort_keys=False, allow_unicode=True))


class PlainReporter(Reporter):
  def __init__(self, echo: Callable[[str], None], now: Callable[[], datetime] = datetime.now, clock: Callable[[], float] = time.monotonic,
               interval: float = HEARTBEAT_SECONDS, heartbeat: bool = True):
    self.echo = echo
    self.now = now
    self.clock = clock
    self.interval = interval
    self.lock = threading.Lock()
    self.width = 0
    # task -> (started, next heartbeat)
    self.running: dict[str, tuple[float, float]] = {}
    self.stop = threading.Event()
    self.thread = threading.Thread(target=self._beat, daemon=True) if heartbeat else None

  def _say(self, mark: str, task: str, text: str = "") -> None:
    line = f"{self.now().strftime('%H:%M:%S')} {mark} {task:<{self.width}}  {text}".rstrip()
    with self.lock:
      self.echo(line)

  def planned(self, names: list[str]) -> None:
    self.width = max((len(name) for name in names), default=0)
    if self.thread:
      self.thread.start()

  def started(self, task: str) -> None:
    now = self.clock()
    with self.lock:
      self.running[task] = (now, now + self.interval)
    self._say("▶", task)

  def note(self, task: str, message: str) -> None:
    self._say("·", task, message)

  def finished(self, task: str, seconds: float) -> None:
    with self.lock:
      self.running.pop(task, None)
    self._say("✓", task, f"{duration(seconds):>7}")

  def failed(self, task: str, seconds: float, error: BaseException, first: bool) -> None:
    with self.lock:
      self.running.pop(task, None)
    # Only the cause: the steps it stopped would read as more failures.
    if first:
      self._say("✗", task, f"{duration(seconds):>7}")

  def tick(self) -> None:
    now = self.clock()
    with self.lock:
      due = [(task, started) for task, (started, beat) in self.running.items() if now >= beat]
      for task, started in due:
        self.running[task] = (started, now + self.interval)
    for task, started in due:
      self._say("…", task, f"still running [{duration(now - started)}]")

  def _beat(self) -> None:
    while not self.stop.wait(1):
      self.tick()

  def close(self) -> None:
    self.stop.set()
    if self.thread and self.thread.is_alive():
      self.thread.join()
