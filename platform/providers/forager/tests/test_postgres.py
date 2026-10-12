import pytest

from forager_provider.postgres import OWNER, Bind, Compose, InvalidName, Provision, object_name

NAME = object_name({"metadata": {"name": "demo.reviews.db"}, "spec": {"instance": "reviews", "resource": "db"}})


class FakeSecrets:
  def __init__(self):
    self.values = {}

  def get(self, key):
    return self.values.get(key)

  def put(self, key, value):
    self.values[key] = value

  def delete(self, key):
    self.values.pop(key, None)


class FakeVcluster:
  def __init__(self, ready=0, existing=None):
    self.applied, self.deleted, self.ready, self.existing = [], [], ready, existing or {}

  def apply(self, obj, manager):
    self.applied.append(obj)

  def get(self, api_version, kind, namespace, name):
    if (kind, namespace) in self.existing:
      return self.existing[(kind, namespace)]
    if kind == "StatefulSet" and self.applied:
      return {"metadata": {"annotations": {OWNER: "demo.reviews.db"}}, "status": {"readyReplicas": self.ready}}
    return None

  def delete(self, api_version, kind, namespace, name):
    self.deleted.append((kind, namespace, name))


def request(instance="reviews", resource="db"):
  return {"metadata": {"name": f"demo.{instance}.{resource}"}, "spec": {"environment": "demo", "instance": instance, "resource": resource}}


def test_names_are_injective_and_readable():
  assert NAME.startswith("reviews-db-") and len(NAME) == len("reviews-db-") + 8
  # "a" + "b-db" and "a-b" + "db" read the same and never share objects.
  assert object_name(request("a", "b-db")) != object_name(request("a-b", "db"))
  assert len(object_name(request("x" * 63, "y" * 63))) <= 63


def test_provision_applies_and_waits():
  secrets, vcluster = FakeSecrets(), FakeVcluster()
  state, _, outputs, secret_ref = Provision().ensure(request(), {}, vcluster, secrets)
  assert state == "Provisioning"
  assert [(obj["kind"], obj["metadata"].get("namespace", obj["metadata"]["name"])) for obj in vcluster.applied] == [
    ("Namespace", "resources"), ("Namespace", "apps"), ("Secret", "apps"), ("Secret", "resources"), ("StatefulSet", "resources"), ("Service", "resources"),
  ]
  assert {obj["metadata"]["name"] for obj in vcluster.applied if obj["kind"] != "Namespace"} == {NAME}
  assert outputs == {"host": f"{NAME}.resources", "port": 5432, "name": "app", "database": "app", "username": "app"}
  assert secret_ref == {"name": NAME, "keys": ["password"]}
  password = secrets.values["demo.reviews.db"]
  assert vcluster.applied[2]["stringData"] == {"password": password}
  # The password is generated once: the next pass writes the same one.
  Provision().ensure(request(), {}, FakeVcluster(), secrets)
  assert secrets.values["demo.reviews.db"] == password


def test_provision_ready():
  vcluster = FakeVcluster(ready=1)
  Provision().ensure(request(), {}, vcluster, FakeSecrets())
  state, message, _, _ = Provision().ensure(request(), {}, vcluster, FakeSecrets())
  assert (state, message) == ("Ready", f"postgres {NAME} ready in demo")


def test_an_object_of_someone_else_is_never_taken_over():
  vcluster = FakeVcluster(existing={("Secret", "apps"): {"metadata": {"name": NAME}}})
  with pytest.raises(InvalidName, match=f"Secret apps/{NAME} already exists"):
    Provision().ensure(request(), {}, vcluster, FakeSecrets())
  assert vcluster.applied == []


def test_the_pods_never_join_the_service_of_the_workload():
  vcluster = FakeVcluster()
  Provision().ensure(request(), {}, vcluster, FakeSecrets())
  service = vcluster.applied[-1]
  assert service["metadata"]["namespace"] == "resources"
  assert service["spec"]["selector"] == {"app.kubernetes.io/name": "postgres", "app.kubernetes.io/instance": NAME}


def test_invalid_name_is_refused_before_anything_is_applied():
  vcluster = FakeVcluster()
  with pytest.raises(InvalidName):
    Provision().ensure(request(resource="Bad_Name"), {}, vcluster, FakeSecrets())
  assert vcluster.applied == []


def test_delete_undoes_only_what_it_owns():
  secrets = FakeSecrets()
  mine = {"metadata": {"annotations": {OWNER: "demo.reviews.db"}}}
  vcluster = FakeVcluster(existing={("Service", "resources"): mine, ("StatefulSet", "resources"): mine, ("Secret", "resources"): mine, ("Secret", "apps"): {"metadata": {}}})
  secrets.put("demo.reviews.db", "secret")
  Provision().delete(request(), vcluster, secrets)
  assert vcluster.deleted == [("Service", "resources", NAME), ("StatefulSet", "resources", NAME), ("Secret", "resources", NAME)]
  assert secrets.values == {}


def test_delete_with_the_environment_gone_only_forgets_the_password():
  secrets = FakeSecrets()
  secrets.put("demo.reviews.db", "secret")
  Provision().delete(request(), None, secrets)
  assert secrets.values == {}


class FakeServer:
  def __init__(self, claimed_by=None):
    self.claim, self.ensured, self.dropped = claimed_by, [], []

  def claimed_by(self, name):
    return self.claim

  def ensure(self, name, password, owner):
    self.ensured.append((name, password, owner))
    self.claim = owner

  def drop(self, name):
    self.dropped.append(name)
    self.claim = None


class FakeInstances:
  def __init__(self, server):
    self.server, self.asked = server, []

  def of(self, instance):
    self.asked.append(instance)
    return self.server


def composed(params=None):
  obj = request()
  obj["spec"]["params"] = {"instance": "shared-pg"} if params is None else params
  return obj


def test_compose_makes_a_database_in_the_shared_instance():
  server, secrets, vcluster = FakeServer(), FakeSecrets(), FakeVcluster()
  instances = FakeInstances(server)
  state, message, outputs, secret_ref = Compose(instances).ensure(composed(), {"instance": "shared-pg"}, vcluster, secrets)
  assert (state, message) == ("Ready", f"database {NAME} ready in shared-pg")
  assert instances.asked == ["shared-pg"]
  password = secrets.values["demo.reviews.db"]
  assert server.ensured == [(NAME, password, "demo.reviews.db")]
  assert outputs == {"host": "shared-pg.resources", "port": 5432, "name": NAME, "database": NAME, "username": NAME}
  assert secret_ref == {"name": NAME, "keys": ["password"]}
  secret = vcluster.applied[-1]
  assert (secret["kind"], secret["metadata"]["namespace"], secret["stringData"]) == ("Secret", "apps", {"password": password})
  assert secret["metadata"]["annotations"] == {OWNER: "demo.reviews.db"}
  # Again: the same password, nothing new.
  Compose(instances).ensure(composed(), {"instance": "shared-pg"}, vcluster, secrets)
  assert server.ensured[-1] == (NAME, password, "demo.reviews.db")


@pytest.mark.parametrize("params", [{}, {"instance": "shared_pg"}, {"instance": "a; DROP DATABASE x"}])
def test_compose_needs_a_valid_shared_instance(params):
  instances = FakeInstances(FakeServer())
  with pytest.raises(InvalidName, match="shared instance"):
    Compose(instances).ensure(composed(params), params, FakeVcluster(), FakeSecrets())
  assert instances.asked == []


@pytest.mark.parametrize("claim", ["", "other.reviews.db"])
def test_compose_never_takes_a_database_of_someone_else(claim):
  server, vcluster = FakeServer(claimed_by=claim), FakeVcluster()
  with pytest.raises(InvalidName, match="belongs to something else"):
    Compose(FakeInstances(server)).ensure(composed(), {"instance": "shared-pg"}, vcluster, FakeSecrets())
  assert server.ensured == [] and vcluster.applied == []


def test_compose_never_takes_a_secret_of_someone_else():
  server, vcluster = FakeServer(), FakeVcluster(existing={("Secret", "apps"): {"metadata": {"name": NAME}}})
  with pytest.raises(InvalidName, match=f"Secret apps/{NAME}"):
    Compose(FakeInstances(server)).ensure(composed(), {"instance": "shared-pg"}, vcluster, FakeSecrets())
  assert server.ensured == []


def test_compose_delete_drops_what_it_owns():
  server, secrets = FakeServer(claimed_by="demo.reviews.db"), FakeSecrets()
  secrets.put("demo.reviews.db", "secret")
  vcluster = FakeVcluster(existing={("Secret", "apps"): {"metadata": {"annotations": {OWNER: "demo.reviews.db"}}}})
  Compose(FakeInstances(server)).delete(composed(), vcluster, secrets)
  assert server.dropped == [NAME]
  assert vcluster.deleted == [("Secret", "apps", NAME)]
  assert secrets.values == {}


def test_compose_delete_outlives_the_environment_and_spares_others():
  # The vcluster is gone, the shared instance is not: the database is still dropped.
  server = FakeServer(claimed_by="demo.reviews.db")
  Compose(FakeInstances(server)).delete(composed(), None, FakeSecrets())
  assert server.dropped == [NAME]
  other = FakeServer(claimed_by="other.reviews.db")
  Compose(FakeInstances(other)).delete(composed(), None, FakeSecrets())
  assert other.dropped == []


def test_compose_delete_without_a_valid_instance_only_releases():
  instances, secrets = FakeInstances(FakeServer()), FakeSecrets()
  secrets.put("demo.reviews.db", "secret")
  Compose(instances).delete(composed({}), None, secrets)
  assert instances.asked == [] and secrets.values == {}


class FakeSources:
  """Secrets a bind may copy: name -> password, or None for one without the bindable label."""

  def __init__(self, secrets=None):
    self.secrets, self.asked = secrets if secrets is not None else {"restored-db": "restored-secret"}, []

  def password(self, name):
    self.asked.append(name)
    if name not in self.secrets:
      raise InvalidName(f"Secret {name} not found")
    if self.secrets[name] is None:
      raise InvalidName(f"Secret {name} is not bindable")
    return self.secrets[name]


BIND = {"secretRef": "restored-db", "host": "shared-pg.resources", "port": "5432", "database": "restored", "username": "restored"}


def test_bind_copies_the_existing_secret_and_returns_values():
  secrets, vcluster, sources = FakeSecrets(), FakeVcluster(), FakeSources()
  state, message, outputs, secret_ref = Bind(sources).ensure(request(), BIND, vcluster, secrets)
  assert (state, message) == ("Ready", "bound to restored at shared-pg.resources")
  assert sources.asked == ["restored-db"]
  assert outputs == {"host": "shared-pg.resources", "port": 5432, "name": "restored", "database": "restored", "username": "restored"}
  assert secret_ref == {"name": NAME, "keys": ["password"]}
  secret = vcluster.applied[-1]
  assert (secret["kind"], secret["metadata"]["namespace"], secret["metadata"]["name"], secret["stringData"]) == ("Secret", "apps", NAME, {"password": "restored-secret"})
  assert secret["metadata"]["annotations"] == {OWNER: "demo.reviews.db"}
  # Nothing generated: the credential is the one that exists.
  assert secrets.values == {}


def test_bind_port_defaults_to_5432():
  params = {key: value for key, value in BIND.items() if key != "port"}
  _, _, outputs, _ = Bind(FakeSources()).ensure(request(), params, FakeVcluster(), FakeSecrets())
  assert outputs["port"] == 5432


@pytest.mark.parametrize("field, value", [
  ("secretRef", None), ("host", None), ("database", None), ("username", None),
  ("secretRef", "resource.demo.reviews.db"), ("host", "evil host"), ("port", "54x"), ("database", "a; DROP"), ("username", ""),
])
def test_bind_needs_valid_params(field, value):
  params = {key: v for key, v in BIND.items() if key != field}
  if value is not None:
    params[field] = value
  sources, vcluster = FakeSources(), FakeVcluster()
  with pytest.raises(InvalidName, match=f"params.{field}"):
    Bind(sources).ensure(request(), params, vcluster, FakeSecrets())
  assert sources.asked == [] and vcluster.applied == []


@pytest.mark.parametrize("secrets", [{}, {"restored-db": None}])
def test_bind_copies_only_a_bindable_secret(secrets):
  vcluster = FakeVcluster()
  with pytest.raises(InvalidName, match="Secret restored-db"):
    Bind(FakeSources(secrets)).ensure(request(), BIND, vcluster, FakeSecrets())
  assert vcluster.applied == []


def test_bind_never_takes_a_secret_of_someone_else():
  vcluster = FakeVcluster(existing={("Secret", "apps"): {"metadata": {"name": NAME}}})
  with pytest.raises(InvalidName, match=f"Secret apps/{NAME}"):
    Bind(FakeSources()).ensure(request(), BIND, vcluster, FakeSecrets())
  assert vcluster.applied == []


def test_bind_delete_removes_only_the_copy():
  sources = FakeSources()
  vcluster = FakeVcluster(existing={("Secret", "apps"): {"metadata": {"annotations": {OWNER: "demo.reviews.db"}}}})
  Bind(sources).delete(request(), vcluster, FakeSecrets())
  assert vcluster.deleted == [("Secret", "apps", NAME)]
  assert sources.asked == []
  other = FakeVcluster(existing={("Secret", "apps"): {"metadata": {"annotations": {OWNER: "other.reviews.db"}}}})
  Bind(sources).delete(request(), other, FakeSecrets())
  Bind(sources).delete(request(), None, FakeSecrets())
  assert other.deleted == []
