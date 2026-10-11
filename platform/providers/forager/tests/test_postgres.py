import pytest

from forager_provider.postgres import OWNER, InvalidName, Provision, object_name

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
