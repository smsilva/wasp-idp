"""In-memory StateWriter/StateReader for API tests: one store per plural, like one CRD per plural."""
import json
from collections import defaultdict

from platform_api.state import ENVIRONMENTS, AlreadyExists, Conflict, NotFound
from platform_api.teams import TeamExists, TeamsUnavailable


def _copy(obj: dict) -> dict:
  return json.loads(json.dumps(obj))


class FakeState:
  def __init__(self):
    self.stores = defaultdict(dict)
    self.version = 0
    self.on_create = None
    self.before_delete = None

  @property
  def objects(self) -> dict:
    """The environments store, which test_api.py inspects and mutates directly."""
    return self.stores[ENVIRONMENTS]

  def _bump(self, obj):
    self.version += 1
    obj["metadata"]["resourceVersion"] = str(self.version)

  def create(self, plural, body):
    store = self.stores[plural]
    name = body["metadata"]["name"]
    if name in store:
      raise AlreadyExists(name)
    obj = _copy(body)
    obj["metadata"]["creationTimestamp"] = "2026-10-10T00:00:00Z"
    obj["metadata"]["uid"] = f"uid-{self.version + 1}"
    self._bump(obj)
    store[name] = obj
    created = _copy(obj)
    if self.on_create:
      self.on_create(obj)
    return created

  def replace(self, plural, body):
    store = self.stores[plural]
    name = body["metadata"]["name"]
    if name not in store:
      raise NotFound(name)
    if store[name]["metadata"]["resourceVersion"] != body["metadata"].get("resourceVersion"):
      raise Conflict(name)
    obj = _copy(body)
    self._bump(obj)
    store[name] = obj
    return _copy(obj)

  def replace_status(self, plural, body):
    name = body["metadata"]["name"]
    current = self.stores[plural][name]
    if current["metadata"]["resourceVersion"] != body["metadata"]["resourceVersion"]:
      raise Conflict(name)
    current["status"] = body["status"]
    self._bump(current)
    return _copy(current)

  def delete(self, plural, name, uid=None):
    if self.before_delete:
      self.before_delete(self)
    store = self.stores[plural]
    if name not in store:
      raise NotFound(name)
    if uid is not None and store[name]["metadata"]["uid"] != uid:
      raise Conflict(name)
    del store[name]

  def get(self, plural, name):
    store = self.stores[plural]
    if name not in store:
      raise NotFound(name)
    return _copy(store[name])

  def list(self, plural):
    return [_copy(obj) for obj in self.stores[plural].values()]


class FakeTeams:
  """The team directory the routes use (KeycloakTeams), in memory."""

  def __init__(self, *names):
    self.teams = set(names)
    self.down = False

  def names(self):
    if self.down:
      raise TeamsUnavailable("Keycloak unreachable")
    return sorted(self.teams)

  def create(self, name):
    if name in self.teams:
      raise TeamExists(name)
    self.teams.add(name)


# The teams of idp/catalog/org.yaml, which most catalog tests use as owners.
CATALOG_TEAMS = ("team-alpha", "team-beta", "team-platform")
