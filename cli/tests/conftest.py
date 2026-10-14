import threading

import pytest

from wasp_platform.bootstrap.tasks import Reporter


class Recorder(Reporter):
  """Keeps every event of a run as a tuple: (event, task, *args)."""

  def __init__(self):
    self.events = []
    self.lock = threading.Lock()

  def __getattribute__(self, name):
    if name in Reporter.__dict__ and not name.startswith("_") and name != "close":
      return lambda *args: self._keep(name, *args)
    return object.__getattribute__(self, name)

  def _keep(self, *event):
    with self.lock:
      self.events.append(event)

  def of(self, task):
    return [event for event in self.events if len(event) > 1 and event[1] == task]


@pytest.fixture
def recorder():
  return Recorder()
