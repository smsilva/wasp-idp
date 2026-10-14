"""Wall time of each step of `platform init` (#442): the baseline that #437 is measured against."""
import time
from contextlib import contextmanager


class Timings:
  def __init__(self, clock=time.monotonic):
    self.clock = clock
    self.start = clock()
    self.steps: list[tuple[str, float]] = []

  @contextmanager
  def step(self, name: str):
    """Records the step even when it fails: a slow timeout is what the summary must show."""
    started = self.clock()
    try:
      yield
    finally:
      self.steps.append((name, self.clock() - started))

  def total(self) -> float:
    return self.clock() - self.start

  def as_dict(self) -> dict:
    return {
      "steps": [{"step": name, "seconds": round(seconds, 1)} for name, seconds in self.steps],
      "total_seconds": round(self.total(), 1),
    }


def duration(seconds: float) -> str:
  if seconds < 60:
    return f"{seconds:.1f}s"
  minutes, rest = divmod(round(seconds), 60)
  return f"{minutes}m{rest:02d}s"


def summary(timings: Timings) -> list[str]:
  rows = [(name, duration(seconds)) for name, seconds in timings.steps] + [("total", duration(timings.total()))]
  name_width = max(len(name) for name, _ in rows)
  time_width = max(len(text) for _, text in rows)
  return [f"{name:<{name_width}}  {text:>{time_width}}" for name, text in rows]
