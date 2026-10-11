import copy
from datetime import datetime, timezone

from forager_provider.reconciler import FINALIZER, Reconciler
from test_policy import DEFAULT, policy
from test_postgres import FakeSecrets

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


class FakeStore:
  def __init__(self, resources=None, component=True, environment_ready=True):
    self.environment = {
      "metadata": {"name": "demo", "uid": "uid-demo"},
      "status": {"port": 7100, "kubeconfigData": "kubeconfig", "conditions": [{"type": "Ready", "status": "True" if environment_ready else "False"}]},
    }
    app_spec = {"apiVersion": "score.dev/v1b1", "containers": {"api": {"image": "."}}}
    if resources is not None:
      app_spec["resources"] = resources
    self.versions = {"reviews.2.1.0": {"spec": {"appSpec": app_spec}}}
    self.components = {"reviews": {"spec": {"owner": "team-alpha", "system": "bookinfo"}}} if component else {}
    self.created, self.catalog, self.patches, self.status_patches = {}, [], [], []

  def get_environment(self, name):
    return self.environment if name == "demo" else None

  def get_version(self, name):
    return self.versions.get(name)

  def get_component(self, name):
    return self.components.get(name)

  def create_catalog_resource(self, body):
    self.catalog.append(body)

  def create_request(self, body):
    self.created[body["metadata"]["name"]] = body
    return copy.deepcopy(body)

  def patch_request(self, name, patch):
    self.patches.append((name, patch))

  def patch_request_status(self, name, status):
    self.status_patches.append((name, status))


class FakeProvisioner:
  def __init__(self, state="Provisioning"):
    self.state, self.ensured, self.deleted = state, [], []

  def ensure(self, request, params, vcluster, secrets):
    self.ensured.append((request["metadata"]["name"], params))
    return self.state, f"postgres {self.state}", {"host": "reviews-db.apps"}, {"name": "reviews-db", "keys": ["password"]}

  def delete(self, request, vcluster, secrets):
    self.deleted.append(request["metadata"]["name"])


class FakeVclusters:
  def of(self, environment):
    return object()


def revision(number=1, action="deploy", ready=None, overrides=None):
  obj = {"metadata": {"name": f"demo.reviews.{number}"}, "spec": {
    "environment": "demo", "instance": "reviews", "component": "reviews", "revision": number, "action": action, "version": "2.1.0",
  }}
  if overrides:
    obj["spec"]["overrides"] = overrides
  if ready:
    obj["status"] = {"conditions": [{"type": "Ready", "status": ready[0], "reason": ready[1]}]}
  return obj


def reconciler(store, provisioner, secrets=None):
  return Reconciler(store, FakeVclusters(), secrets or FakeSecrets(), provisioners={"postgres/provision": provisioner}, now=lambda: NOW)


def conditions(store, name):
  return {c["type"]: c for c in [patch for patch_name, patch in store.status_patches if patch_name == name][-1].get("conditions", [])}


def test_resolves_creates_and_provisions():
  store, provisioner = FakeStore(resources={"db": {"type": "postgres"}}), FakeProvisioner()
  assert reconciler(store, provisioner).reconcile([revision()], [], [DEFAULT]) is True
  request = store.created["demo.reviews.db"]
  assert request["spec"] == {"environment": "demo", "instance": "reviews", "component": "reviews", "resource": "db", "type": "postgres", "mode": "provision", "provisioner": "postgres/provision", "params": {}}
  assert request["metadata"]["finalizers"] == [FINALIZER]
  assert request["metadata"]["ownerReferences"][0]["uid"] == "uid-demo"
  first = store.status_patches[0][1]
  assert first["revision"] == 1
  assert [(c["type"], c["status"], c["reason"]) for c in first["conditions"]] == [("Resolved", "True", "Resolved"), ("Ready", "Unknown", "Provisioning")]
  # Provisioned in the same pass.
  assert provisioner.ensured == [("demo.reviews.db", {})]
  assert store.status_patches[-1][1]["outputs"] == {"host": "reviews-db.apps"}
  assert store.status_patches[-1][1]["secretRef"] == {"name": "reviews-db", "keys": ["password"]}


def test_derives_the_catalog_resource_without_id():
  store = FakeStore(resources={"db": {"type": "postgres"}, "shared": {"type": "postgres", "id": "orders-db"}})
  reconciler(store, FakeProvisioner()).reconcile([revision()], [], [DEFAULT])
  assert [body["metadata"]["name"] for body in store.catalog] == ["reviews-db"]
  assert store.catalog[0]["spec"] == {"owner": "team-alpha", "system": "bookinfo", "type": "postgres", "description": "db of reviews, derived from its Score"}


def test_no_component_no_catalog_resource():
  store = FakeStore(resources={"db": {"type": "postgres"}}, component=False)
  reconciler(store, FakeProvisioner()).reconcile([revision()], [], [DEFAULT])
  assert store.catalog == [] and "demo.reviews.db" in store.created


def test_a_resource_without_provider_holds_back_the_others():
  store, provisioner = FakeStore(resources={"db": {"type": "postgres"}, "dns": {"type": "dns"}}), FakeProvisioner()
  reconciler(store, provisioner).reconcile([revision()], [], [DEFAULT])
  assert "mode" not in store.created["demo.reviews.dns"]["spec"]
  dns = conditions(store, "demo.reviews.dns")
  assert (dns["Resolved"]["status"], dns["Resolved"]["reason"]) == ("False", "NoProviderForCapability")
  assert dns["Resolved"]["message"] == "dns: no provisioner for dns in demo"
  db = conditions(store, "demo.reviews.db")
  assert (db["Ready"]["reason"], db["Ready"]["message"]) == ("Waiting", "waiting for the other resources of revision 1")
  assert provisioner.ensured == []


def test_class_from_the_revision_override():
  store = FakeStore(resources={"db": {"type": "postgres"}})
  reconciler(store, FakeProvisioner()).reconcile([revision(overrides={"resources": {"db": {"class": "restored"}}})], [], [DEFAULT])
  assert conditions(store, "demo.reviews.db")["Resolved"]["message"] == "db: no provisioner for postgres class restored in demo"


def existing(mode="provision", ready="True", revision_number=1):
  return {
    "metadata": {"name": "demo.reviews.db", "finalizers": [FINALIZER]},
    "spec": {"environment": "demo", "instance": "reviews", "component": "reviews", "resource": "db", "type": "postgres", "mode": mode, "provisioner": f"postgres/{mode}"},
    "status": {"revision": revision_number, "conditions": [
      {"type": "Resolved", "status": "True", "reason": "Resolved", "message": f"db: postgres/{mode}", "revision": revision_number},
      {"type": "Ready", "status": ready, "reason": "Ready" if ready == "True" else "Provisioning", "message": "postgres True"},
    ]},
  }


def test_a_new_revision_reuses_the_ready_request():
  store, provisioner = FakeStore(resources={"db": {"type": "postgres"}}), FakeProvisioner()
  reconciler(store, provisioner).reconcile([revision(1, ready=("True", "Succeeded")), revision(2)], [existing()], [DEFAULT])
  assert store.created == {} and provisioner.ensured == []
  patch = store.status_patches[0][1]
  assert patch["revision"] == 2
  assert [(c["type"], c["status"]) for c in patch["conditions"]] == [("Resolved", "True"), ("Ready", "True")]


def test_nothing_to_write_when_nothing_changed():
  store = FakeStore(resources={"db": {"type": "postgres"}})
  assert reconciler(store, FakeProvisioner()).reconcile([revision(2)], [existing(revision_number=2)], [DEFAULT]) is True
  assert store.status_patches == [] and store.patches == []


def test_a_mode_change_is_refused():
  store, provisioner = FakeStore(resources={"db": {"type": "postgres"}}), FakeProvisioner()
  compose = policy("demo", [{"type": "postgres", "mode": "compose"}], environment="demo")
  rec = Reconciler(store, FakeVclusters(), FakeSecrets(), provisioners={"postgres/provision": provisioner, "postgres/compose": provisioner}, now=lambda: NOW)
  rec.reconcile([revision(2)], [existing()], [DEFAULT, compose])
  resolved = conditions(store, "demo.reviews.db")["Resolved"]
  assert (resolved["status"], resolved["reason"], resolved["revision"]) == ("False", "ResourceModeChanged", 2)
  assert resolved["message"] == "db is provision and the policy now resolves it as compose: remove the workload and deploy again to change it"
  assert store.patches == [] and provisioner.ensured == []


def test_closed_and_remove_revisions_are_not_resolved():
  store = FakeStore(resources={"db": {"type": "postgres"}})
  assert reconciler(store, FakeProvisioner()).reconcile([revision(1, ready=("True", "Succeeded")), revision(2, action="remove")], [], [DEFAULT]) is False
  assert store.created == {}


def test_provisioning_waits_for_the_environment():
  store, provisioner = FakeStore(resources={"db": {"type": "postgres"}}, environment_ready=False), FakeProvisioner()
  assert reconciler(store, provisioner).reconcile([], [existing(ready="Unknown")], [DEFAULT]) is True
  assert provisioner.ensured == []


def test_provisioned_becomes_ready():
  store = FakeStore()
  assert reconciler(store, FakeProvisioner(state="Ready")).reconcile([], [existing(ready="Unknown")], [DEFAULT]) is False
  ready = conditions(store, "demo.reviews.db")["Ready"]
  assert (ready["status"], ready["reason"]) == ("True", "Ready")


def test_delete_undoes_and_releases():
  store, provisioner = FakeStore(), FakeProvisioner()
  request = existing()
  request["metadata"]["deletionTimestamp"] = "2026-10-11T12:00:00Z"
  reconciler(store, provisioner).reconcile([], [request], [DEFAULT])
  assert provisioner.deleted == ["demo.reviews.db"]
  assert store.patches == [("demo.reviews.db", {"metadata": {"finalizers": []}})]


def test_delete_with_the_environment_gone_only_releases():
  store, provisioner, secrets = FakeStore(), FakeProvisioner(), FakeSecrets()
  store.environment["metadata"]["deletionTimestamp"] = "2026-10-11T12:00:00Z"
  secrets.put("demo.reviews.db", "secret")
  request = existing()
  request["metadata"]["deletionTimestamp"] = "2026-10-11T12:00:00Z"
  reconciler(store, provisioner, secrets).reconcile([], [request], [DEFAULT])
  assert provisioner.deleted == [] and secrets.values == {}
  assert store.patches == [("demo.reviews.db", {"metadata": {"finalizers": []}})]
