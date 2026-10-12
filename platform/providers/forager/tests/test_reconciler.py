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
    self.state, self.ensured, self.deleted, self.vclusters = state, [], [], []

  def ensure(self, request, params, vcluster, secrets):
    self.ensured.append((request["metadata"]["name"], params))
    return self.state, f"postgres {self.state}", {"host": "reviews-db.apps"}, {"name": "reviews-db", "keys": ["password"]}

  def delete(self, request, vcluster, secrets):
    self.deleted.append(request["metadata"]["name"])
    self.vclusters.append(vcluster)


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


def test_a_class_change_is_refused():
  # Same mode, another class: reusing the request would leave the branch on the old database.
  store, provisioner = FakeStore(resources={"db": {"type": "postgres"}}), FakeProvisioner()
  restored = policy("demo", [{"type": "postgres", "class": "restored", "mode": "provision"}], environment="demo")
  reconciler(store, provisioner).reconcile([revision(2, overrides={"resources": {"db": {"class": "restored"}}})], [existing()], [DEFAULT, restored])
  resolved = conditions(store, "demo.reviews.db")["Resolved"]
  assert (resolved["status"], resolved["reason"]) == ("False", "ResourceModeChanged")
  assert resolved["message"] == "db is class (none) and the revision now asks for class restored: remove the workload and deploy again to change it"
  assert store.patches == [] and provisioner.ensured == []


def test_a_late_resolution_takes_the_class_of_the_revision():
  store, provisioner = FakeStore(resources={"db": {"type": "postgres"}}), FakeProvisioner()
  unresolved = existing()
  unresolved["spec"] = {key: value for key, value in unresolved["spec"].items() if key not in ("mode", "provisioner")} | {"class": "old"}
  restored = policy("demo", [{"type": "postgres", "class": "restored", "mode": "provision"}], environment="demo")
  reconciler(store, provisioner).reconcile([revision(2, overrides={"resources": {"db": {"class": "restored"}}})], [unresolved], [DEFAULT, restored])
  assert store.patches == [("demo.reviews.db", {"spec": {"mode": "provision", "provisioner": "postgres/provision", "params": {}, "class": "restored"}})]


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


def test_delete_with_the_environment_gone_has_no_vcluster():
  store, provisioner, secrets = FakeStore(), FakeProvisioner(), FakeSecrets()
  store.environment["metadata"]["deletionTimestamp"] = "2026-10-11T12:00:00Z"
  secrets.put("demo.reviews.db", "secret")
  request = existing()
  request["metadata"]["deletionTimestamp"] = "2026-10-11T12:00:00Z"
  reconciler(store, provisioner, secrets).reconcile([], [request], [DEFAULT])
  # The provisioner still undoes what lives outside the vcluster (compose), without one.
  assert provisioner.deleted == ["demo.reviews.db"] and provisioner.vclusters == [None]
  assert store.patches == [("demo.reviews.db", {"metadata": {"finalizers": []}})]


class Recording:
  """A provisioner that records the params it got and returns outputs from them."""

  def __init__(self, outputs=None):
    self.calls, self.outputs = [], outputs or {}

  def ensure(self, request, params, vcluster, secrets):
    self.calls.append((request["metadata"]["name"], params))
    return "Ready", "ok", dict(self.outputs), None

  def delete(self, request, vcluster, secrets):
    pass


ROUTE = {"type": "route", "params": {"host": "${resources.dns.host}", "path": "/", "port": 80}}
DEFAULT_ROUTING = policy("platform-default", [{"type": "postgres", "mode": "provision"}, {"type": "dns", "mode": "provision"}, {"type": "route", "mode": "provision"}])


def routing_reconciler(store):
  dns, route = Recording({"host": "reviews.demo.localhost"}), Recording({"url": "http://reviews.demo.localhost:7080/"})
  return Reconciler(store, FakeVclusters(), FakeSecrets(), provisioners={"dns/provision": dns, "route/provision": route}, now=lambda: NOW), dns, route


def test_score_params_go_to_the_request():
  store = FakeStore(resources={"dns": {"type": "dns"}, "route": ROUTE})
  routing_reconciler(store)[0].reconcile([revision()], [], [DEFAULT_ROUTING])
  assert store.created["demo.reviews.route"]["spec"]["scoreParams"] == {"host": "${resources.dns.host}", "path": "/", "port": 80}
  assert "scoreParams" not in store.created["demo.reviews.dns"]["spec"]


def test_a_reference_waits_for_the_resource_it_points_at():
  # dns sorts before route: in the same pass it is Ready first, and the route gets its host.
  store = FakeStore(resources={"dns": {"type": "dns"}, "route": ROUTE})
  reconciler, dns, route = routing_reconciler(store)
  reconciler.reconcile([revision()], [], [DEFAULT_ROUTING])
  assert route.calls == [("demo.reviews.route", {"host": "reviews.demo.localhost", "path": "/", "port": 80})]


def test_a_reference_to_a_resource_not_ready_keeps_provisioning():
  store = FakeStore(resources={"dns": {"type": "dns"}, "route": ROUTE})
  reconciler, dns, route = routing_reconciler(store)
  waiting = {
    "metadata": {"name": "demo.reviews.route", "finalizers": [FINALIZER]},
    "spec": {"environment": "demo", "instance": "reviews", "component": "reviews", "resource": "route", "type": "route", "mode": "provision", "provisioner": "route/provision", "scoreParams": ROUTE["params"]},
    "status": {"revision": 1, "conditions": [{"type": "Ready", "status": "Unknown", "reason": "Provisioning", "message": "provisioning"}]},
  }
  assert reconciler.reconcile([], [waiting], [DEFAULT_ROUTING]) is True
  assert route.calls == []
  ready = conditions(store, "demo.reviews.route")["Ready"]
  assert (ready["status"], ready["message"]) == ("Unknown", "waiting for dns")


def test_a_reference_to_an_unknown_output_fails():
  store = FakeStore(resources={"dns": {"type": "dns"}, "route": {"type": "route", "params": {"host": "${resources.dns.address}"}}})
  reconciler, dns, route = routing_reconciler(store)
  reconciler.reconcile([revision()], [], [DEFAULT_ROUTING])
  ready = conditions(store, "demo.reviews.route")["Ready"]
  assert (ready["status"], ready["reason"], ready["message"]) == ("False", "Failed", "dns has no output address")


def test_the_policy_params_win_over_the_score():
  store = FakeStore(resources={"db": {"type": "postgres", "params": {"instance": "mine"}}})
  provisioner = Recording()
  bound = policy("demo", [{"type": "postgres", "mode": "provision", "params": {"instance": "shared-pg"}}], environment="demo")
  Reconciler(store, FakeVclusters(), FakeSecrets(), provisioners={"postgres/provision": provisioner}, now=lambda: NOW).reconcile([revision()], [], [bound])
  assert provisioner.calls == [("demo.reviews.db", {"instance": "shared-pg"})]


def test_new_score_params_provision_the_request_again():
  store = FakeStore(resources={"dns": {"type": "dns"}, "route": {**ROUTE, "params": {**ROUTE["params"], "path": "/v2"}}})
  reconciler, dns, route = routing_reconciler(store)
  ready_route = {
    "metadata": {"name": "demo.reviews.route", "finalizers": [FINALIZER]},
    "spec": {"environment": "demo", "instance": "reviews", "component": "reviews", "resource": "route", "type": "route", "mode": "provision", "provisioner": "route/provision", "scoreParams": ROUTE["params"]},
    "status": {"revision": 1, "outputs": {"url": "http://reviews.demo.localhost:7080/"}, "conditions": [{"type": "Resolved", "status": "True", "reason": "Resolved", "message": "route: route/provision", "revision": 1}, {"type": "Ready", "status": "True", "reason": "Ready", "message": "ok"}]},
  }
  ready_dns = {
    "metadata": {"name": "demo.reviews.dns", "finalizers": [FINALIZER]},
    "spec": {"environment": "demo", "instance": "reviews", "component": "reviews", "resource": "dns", "type": "dns", "mode": "provision", "provisioner": "dns/provision"},
    "status": {"revision": 1, "outputs": {"host": "reviews.demo.localhost"}, "conditions": [{"type": "Resolved", "status": "True", "reason": "Resolved", "message": "dns: dns/provision", "revision": 1}, {"type": "Ready", "status": "True", "reason": "Ready", "message": "ok"}]},
  }
  reconciler.reconcile([revision(1, ready=("True", "Succeeded")), revision(2)], [ready_dns, ready_route], [DEFAULT_ROUTING])
  assert ("demo.reviews.route", {"spec": {"scoreParams": {"host": "${resources.dns.host}", "path": "/v2", "port": 80}}}) in store.patches
  assert route.calls == [("demo.reviews.route", {"host": "reviews.demo.localhost", "path": "/v2", "port": 80})]
  assert dns.calls == []
