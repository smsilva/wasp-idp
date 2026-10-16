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


def previous_run(base: Path) -> dict | None:
  """The newest run that succeeded, read before this run's folder exists: its step times fill the bars."""
  if not base.is_dir():
    return None
  for folder in sorted((path for path in base.iterdir() if path.is_dir() and not path.is_symlink()), reverse=True):
    try:
      record = yaml.safe_load((folder / "run.yaml").read_text())
    except (OSError, yaml.YAMLError):
      continue
    if isinstance(record, dict) and record.get("result") == "succeeded":
      return {"steps": {step["step"]: step["seconds"] for step in record.get("steps", [])}, "total": record.get("totalSeconds")}
  return None


VISIBLE_STEPS = 5
# Gap between the two step columns, and the minimum half-width worth splitting into two: below it, a step name
# plus a "waits <task>" label wraps or truncates, so one column reads better.
STEP_COLUMN_GAP = 4
MIN_COLUMN_WIDTH = 36


def shorter(path: Path) -> str:
  """~ for the home folder: the card is narrow."""
  home = Path.home()
  return f"~/{path.relative_to(home)}" if path.is_relative_to(home) else str(path)


def settings_file(settings: list[tuple[str, str, str]]) -> str | None:
  """The settings file the rows came from, if any: the card names it once and shows only its file name per row."""
  return next((source for _, _, source in settings if source not in SOURCES), None)


def settings_grid(settings: list[tuple[str, str, str]]):
  from rich.table import Table

  grid = Table.grid(padding=(0, 2))
  grid.add_column(style="dim")
  grid.add_column()
  grid.add_column(style="dim")
  for name, value, source in settings:
    grid.add_row(name, value, source if source in SOURCES else Path(source).name)
  return grid


def frame(title: str, subtitle: str, *parts, width: int):
  """The outer card of `platform init`: the title, a dim subtitle, then the sections."""
  from rich.console import Group
  from rich.panel import Panel
  from rich.text import Text

  return Panel(Group(Text(title, style="bold"), Text(subtitle, style="dim"), *parts), width=width, padding=(0, 1))


def card_width(console) -> int:
  """The width of the bars: the card fits a narrow terminal and stops growing at 116."""
  return max(min(console.width - 12, 116), 10)


def settings_card(console, settings: list[tuple[str, str, str]]):
  """What init shows before Proceed?: the top of the card the run then fills."""
  source = settings_file(settings)
  return frame("platform init", f"settings from {shorter(Path(source))}" if source else "settings", "", settings_grid(settings), "", width=card_width(console) + 12)
BAR = "▍"
DONE, RUNNING, LEFT, FAILED, WARNING = "green", "blue", "grey37", "red", "yellow"
# A note that starts with this is a warning: it gets ⚠ and the warning colour in the card.
WARNING_PREFIX = "warning: "
SOURCES = ("flag", "default", "cluster")
# A running bar stops here until its step ends: the previous run is a guess, not a promise.
BAR_CAP = 0.95


class LiveReporter(Reporter):
  """The card of `platform init` on a terminal (#458): the steps running now and the next to start,
  each with a bar that fills by the step's time in the previous run, and the whole run below."""

  def __init__(self, console, folder: Path, previous: dict | None, subtitle: str, settings: list[tuple[str, str, str]] | None = None,
               clock: Callable[[], float] = time.monotonic, live: bool = True):
    from rich.live import Live

    self.console = console
    self.folder = folder
    self.previous = previous or {"steps": {}, "total": None}
    self.settings = settings or []
    source = settings_file(self.settings)
    self.subtitle = f"{subtitle} · settings from {shorter(Path(source))}" if source else subtitle
    self.clock = clock
    self.notes: list[tuple[str, str]] = []
    self.lock = threading.Lock()
    self.started_at = clock()
    self.needs: dict[str, tuple[str, ...]] = {}
    self.state: dict[str, str] = {}
    self.began: dict[str, float] = {}
    self.took: dict[str, float] = {}
    self.ended: float | None = None
    self.live = Live(console=console, get_renderable=self.render, refresh_per_second=8, transient=False) if live else None

  def planned(self, needs: dict[str, tuple[str, ...]]) -> None:
    with self.lock:
      self.needs = dict(needs)
      self.width = max((len(name) for name in needs), default=0)
      self.state = {name: "waiting" for name in needs}
    if self.live:
      self.live.start()

  def started(self, task: str) -> None:
    with self.lock:
      self.state[task] = "running"
      self.began[task] = self.clock()

  def note(self, task: str, message: str) -> None:
    # In the card, below the run: a warning (no Google login, an expiring credential) stays on screen.
    with self.lock:
      self.notes.append((task, message))

  def finished(self, task: str, seconds: float) -> None:
    with self.lock:
      self.state[task] = "done"
      self.took[task] = seconds

  def failed(self, task: str, seconds: float, error: BaseException, first: bool) -> None:
    with self.lock:
      self.state[task] = "failed" if first else "stopped"
      self.took[task] = seconds

  def close(self) -> None:
    with self.lock:
      self.ended = self.clock()
    if self.live and self.live.is_started:
      self.live.refresh()
      self.live.stop()

  def _elapsed(self) -> float:
    return (self.ended if self.ended is not None else self.clock()) - self.started_at

  def _bar(self, width: int, task: str, now: float):
    from rich.text import Text

    state = self.state[task]
    if state != "running":
      return Text.assemble((BAR * width, {"done": DONE, "failed": FAILED}.get(state, LEFT)))
    elapsed = now - self.began[task]
    last = self.previous["steps"].get(task)
    if last:
      filled = round(width * min(elapsed / last, BAR_CAP)) if last > 0 else round(width * BAR_CAP)
      return Text.assemble((BAR * filled, RUNNING), (BAR * (width - filled), LEFT))
    # No previous run of this step: a block that sweeps the bar.
    block = max(width // 6, 1)
    start = int(elapsed * 8) % (width + block) - block
    return Text.assemble(*((BAR, RUNNING if start <= index < start + block else LEFT) for index in range(width)))

  def _waits(self, task: str) -> str:
    pending = [need for need in self.needs.get(task, ()) if self.state.get(need) != "done"]
    return f"waits {pending[0]}" if pending else ""

  def _step_columns(self, tasks: list[str], width: int, now: float):
    """Two columns of step rows side by side, so a wide terminal shows more at once than it is tall. Falls back
    to one column when the card is too narrow to split."""
    from rich.console import Group
    from rich.table import Table

    column_width = (width - STEP_COLUMN_GAP) // 2
    if len(tasks) <= 1 or column_width < MIN_COLUMN_WIDTH:
      body = []
      for task in tasks:
        body += self._row(task, width, now)
      return Group(*body)

    half = (len(tasks) + 1) // 2
    left, right = tasks[:half], tasks[half:]
    grid = Table.grid()
    grid.add_column(width=column_width)
    grid.add_column(width=STEP_COLUMN_GAP)
    grid.add_column(width=column_width)
    for index, task in enumerate(left):
      other = right[index] if index < len(right) else None
      grid.add_row(Group(*self._row(task, column_width, now)), "", Group(*self._row(other, column_width, now)) if other else "")
    return grid

  def _row(self, task: str, width: int, now: float):
    from rich.table import Table

    head = Table.grid(expand=True, padding=(0, 1, 0, 0))
    head.add_column(ratio=1)
    head.add_column(justify="right")
    state = self.state[task]
    if state == "running":
      right = duration(now - self.began[task])
    elif state == "waiting":
      right = f"[dim]{self._waits(task)}[/dim]"
    else:
      right = duration(self.took[task])
    head.add_row(f"[{FAILED}]{task}[/{FAILED}]" if state == "failed" else task, right)
    return [head, self._bar(width, task, now), ""]

  def _overall(self, width: int):
    from rich.text import Text

    total = len(self.state) or 1
    counts = {state: sum(1 for value in self.state.values() if value == state) for state in ("done", "running", "failed")}
    done = round(width * counts["done"] / total)
    running = round(width * counts["running"] / total)
    failed = round(width * counts["failed"] / total)
    left = max(width - done - running - failed, 0)
    return Text.assemble((BAR * done, DONE), (BAR * failed, FAILED), (BAR * running, RUNNING), (BAR * left, LEFT))

  def _notes(self):
    from rich.table import Table

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim")
    grid.add_column()
    for task, message in self.notes:
      if message.startswith(WARNING_PREFIX):
        grid.add_row(f"[{WARNING}]⚠ {task}[/{WARNING}]", f"[{WARNING}]{message.removeprefix(WARNING_PREFIX)}[/{WARNING}]")
      else:
        grid.add_row(task, message)
    return grid

  def render(self):
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    with self.lock:
      now = self.ended if self.ended is not None else self.clock()
      width = card_width(self.console)
      total = len(self.state)
      done = sum(1 for value in self.state.values() if value == "done")
      running = [task for task in self.state if self.state[task] == "running"]
      running.sort(key=lambda task: self.began[task])
      waiting = [task for task in self.state if self.state[task] == "waiting"]
      failed = [task for task in self.state if self.state[task] == "failed"]
      elapsed = self._elapsed()

      counter = f"[bold]{done} / {total}[/bold]  steps  {duration(elapsed)}"
      if self.ended is None and self.previous.get("total"):
        counter += f"  [dim]~{min(round(100 * elapsed / self.previous['total']), 99)}% of the last run[/dim]"
      body: list = [counter, ""]

      if self.ended is None:
        shown = (running + waiting)[:VISIBLE_STEPS]
        body.append(f"[bold]Now[/bold] · {len(shown)} of {len(running) + len(waiting)}" + ("" if not self.previous["steps"] else "   [dim]bar = time of the last run[/dim]"))
        body.append("")
        body.append(self._step_columns(shown, width, now))
        if len(running) + len(waiting) > len(shown):
          body += [f"[dim]+{len(running) + len(waiting) - len(shown)} more waiting[/dim]", ""]
      elif failed:
        for task in failed:
          body += self._row(task, width, now)
      else:
        slowest = sorted(self.took.items(), key=lambda item: item[1], reverse=True)[:3]
        body.append("[bold]Slowest[/bold]")
        for task, seconds in slowest:
          line = Table.grid(expand=True)
          line.add_column(ratio=1)
          line.add_column(justify="right")
          line.add_row(task, duration(seconds))
          body.append(line)
        body.append("")

      scale = Table.grid(expand=True)
      scale.add_column(ratio=1)
      scale.add_column(justify="right")
      scale.add_row("[dim]0 %[/dim]", "[dim]100 %[/dim]")
      legend = Text.assemble(
        ("■", DONE), f" done {done}   ", ("■", RUNNING), f" running {len(running)}   ", ("■", LEFT), f" waiting {len(waiting)}",
        *((("   ", ""), ("■", FAILED), f" failed {len(failed)}") if failed else ()),
      )
      body += ["[bold]Overall[/bold]", self._overall(width), scale, "", legend, Text(f"logs {shorter(self.folder)}", style="dim", overflow="ellipsis", no_wrap=True)]
      parts = ["", settings_grid(self.settings), ""] if self.settings else [""]
      parts.append(Panel(Group(*body), padding=(1, 2), width=width + 8))
      if self.notes:
        parts += ["", Text("Notes", style="bold"), self._notes()]
      parts.append("")
    return frame("platform init", self.subtitle, *parts, width=width + 12)
