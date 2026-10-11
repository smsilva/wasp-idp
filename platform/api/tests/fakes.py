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


# The shape of the kubeconfig the local_vcluster provider publishes in status.kubeconfigData.
ADMIN_KUBECONFIG = """apiVersion: v1
kind: Config
clusters:
- name: my-vcluster
  cluster:
    server: https://127.0.0.1:7100
    certificate-authority-data: Q0EtREFUQQ==
users:
- name: my-vcluster
  user:
    client-certificate-data: Q0VSVA==
    client-key-data: S0VZ
contexts:
- name: my-vcluster
  context:
    cluster: my-vcluster
    user: my-vcluster
current-context: my-vcluster
"""


class FakeCredentials:
  """The vcluster side of personal credentials (VclusterCredentials), in memory."""

  def __init__(self):
    self.identities = {}  # environment -> set of identity names
    self.down = False

  def issue(self, obj, sub, email):
    from platform_api.credentials import VclusterUnavailable, identity_name

    if self.down:
      raise VclusterUnavailable("vcluster unreachable")
    self.identities.setdefault(obj["metadata"]["name"], set()).add(identity_name(sub))
    return {"token": f"token-of-{sub}", "expirationTimestamp": "2026-10-11T12:10:00Z"}

  def revoke(self, obj, keep=frozenset(), only=None):
    from platform_api.credentials import VclusterUnavailable

    if self.down:
      raise VclusterUnavailable("vcluster unreachable")
    current = self.identities.get(obj["metadata"]["name"], set())
    revoked = sorted(name for name in current if name not in keep and (only is None or name in only))
    current.difference_update(revoked)
    return revoked
