from datetime import datetime, timezone

import pytest

from test_manifests import DIGEST, score
from workload_provider.reconciler import Reconciler

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


class FakeStore:
  def __init__(self, environment_ready=True, app_spec=None):
    self.environments = {"demo": {
      "metadata": {"name": "demo", "uid": "uid-demo"},
      "status": {"port": 7100, "kubeconfigData": "kubeconfig", "conditions": [{"type": "Ready", "status": "True" if environment_ready else "False"}]},
    }}
    self.versions = {
      "reviews.2.1.0": {"spec": {"appSpec": app_spec or score()}},
      "reviews.2.0.0": {"spec": {}},
    }
    self.revision_status, self.instances, self.instance_status, self.deleted_instances = {}, {}, {}, []
    self.requests, self.deleted_requests = {}, []

  def get_resource_request(self, name):
    return self.requests.get(name)

  def delete_resource_requests(self, environment, instance):
    self.deleted_requests.append((environment, instance))

  def get_environment(self, name):
    return self.environments.get(name)

  def get_version(self, name):
    return self.versions.get(name)

  def patch_revision_status(self, name, status):
    self.revision_status.setdefault(name, []).append(status)

  def create_instance(self, body):
    self.instances[body["metadata"]["name"]] = body

  def patch_instance_status(self, name, status):
    self.instance_status.setdefault(name, []).append(status)

  def delete_instance(self, name):
    self.deleted_instances.append(name)


def deployment(desired=1, available=1, ready=None, generation=2, observed=2, deadline=False):
  conditions = [{"type": "Progressing", "reason": "ProgressDeadlineExceeded", "message": "exceeded its progress deadline"}] if deadline else []
  return {
    "metadata": {"generation": generation},
    "spec": {"replicas": desired},
    "status": {"observedGeneration": observed, "replicas": desired, "updatedReplicas": desired, "availableReplicas": available, "readyReplicas": available if ready is None else ready, "conditions": conditions},
  }


class FakeVcluster:
  def __init__(self, state=None, fail=False):
    self.applied, self.deleted, self.state, self.fail = [], [], state, fail

  def apply(self, obj, manager):
    if self.fail:
      raise RuntimeError("connection refused")
    self.applied.append((obj["kind"], obj["metadata"]["name"]))

  def delete(self, api_version, kind, namespace, name):
    if self.fail:
      raise RuntimeError("connection refused")
    self.deleted.append((kind, namespace, name))

  def deployment(self, namespace, name):
    return self.state


class FakeVclusters:
  def __init__(self, vcluster):
    self.vcluster = vcluster

  def of(self, environment):
    return self.vcluster


def revision(number=1, version="2.1.0", reason=None, status=None, action="deploy"):
  obj = {"metadata": {"name": f"demo.reviews.{number}"}, "spec": {
    "environment": "demo", "instance": "reviews", "component": "reviews", "revision": number, "action": action,
    "version": version, "image": "ghcr.io/acme/reviews", "digest": DIGEST,
  }}
  if action == "remove":
    for field in ("version", "image", "digest"):
      del obj["spec"][field]
  if reason:
    obj["status"] = {"conditions": [{"type": "Ready", "status": status, "reason": reason, "message": ""}]}
  return obj


def last(store, name):
  return store.revision_status[name][-1]["conditions"][0]


def reconciler(store, vcluster):
  return Reconciler(store, FakeVclusters(vcluster), now=lambda: NOW)


def test_deploy_succeeds_and_writes_the_instance():
  store, vcluster = FakeStore(), FakeVcluster(deployment())
  assert reconciler(store, vcluster).reconcile([revision()], []) is False
  assert vcluster.applied == [("Namespace", "apps"), ("Deployment", "reviews"), ("Service", "reviews")]
  assert (last(store, "demo.reviews.1")["status"], last(store, "demo.reviews.1")["reason"]) == ("True", "Succeeded")
  assert store.revision_status["demo.reviews.1"][-1]["finishedAt"] == "2026-10-11T12:00:00Z"
  instance = store.instances["demo.reviews"]
  assert instance["metadata"]["ownerReferences"][0]["uid"] == "uid-demo"
  assert instance["spec"] == {"environment": "demo", "instance": "reviews", "component": "reviews"}
  status = store.instance_status["demo.reviews"][-1]
  assert (status["revision"], status["version"], status["url"], status["image"]) == (1, "2.1.0", "http://reviews.apps:80", f"ghcr.io/acme/reviews@{DIGEST}")
  assert status["conditions"][0]["reason"] == "Available"


def test_rollout_in_progress_keeps_the_revision_open():
  store = FakeStore()
  rev = revision()
  assert reconciler(store, FakeVcluster(deployment(desired=2, available=1))).reconcile([rev], []) is True
  condition = last(store, "demo.reviews.1")
  assert (condition["status"], condition["reason"], condition["message"]) == ("Unknown", "Pending", "rolling out: 1/2 replicas available")
  assert store.revision_status["demo.reviews.1"][-1]["startedAt"] == "2026-10-11T12:00:00Z"
  assert store.instances == {}
  # The same state again patches nothing.
  reconciler(store, FakeVcluster(deployment(desired=2, available=1))).reconcile([rev], [])
  assert len(store.revision_status["demo.reviews.1"]) == 1


def test_stale_deployment_status_is_still_progressing():
  store = FakeStore()
  assert reconciler(store, FakeVcluster(deployment(generation=3, observed=2))).reconcile([revision()], []) is True


def test_rollout_failed():
  store = FakeStore()
  reconciler(store, FakeVcluster(deployment(available=0, deadline=True))).reconcile([revision()], [])
  assert last(store, "demo.reviews.1")["reason"] == "RolloutFailed"
  assert store.instance_status["demo.reviews"][-1]["conditions"][0]["reason"] == "Degraded"


def test_environment_not_ready_waits():
  store = FakeStore(environment_ready=False)
  vcluster = FakeVcluster(deployment())
  assert reconciler(store, vcluster).reconcile([revision()], []) is True
  assert (last(store, "demo.reviews.1")["status"], last(store, "demo.reviews.1")["reason"]) == ("Unknown", "EnvironmentNotReady")
  assert vcluster.applied == []


@pytest.mark.parametrize("store,version,reason", [
  (FakeStore(), "2.0.0", "SpecNotIndexed"),
  (FakeStore(), "9.9.9", "SpecNotIndexed"),
  (FakeStore(app_spec=score(extensions={})), "2.1.0", "UnsupportedSpec"),
])
def test_final_failures_apply_nothing(store, version, reason):
  vcluster = FakeVcluster(deployment())
  assert reconciler(store, vcluster).reconcile([revision(version=version)], []) is False
  assert (last(store, "demo.reviews.1")["status"], last(store, "demo.reviews.1")["reason"]) == ("False", reason)
  assert vcluster.applied == []


def test_apply_failed():
  store = FakeStore()
  reconciler(store, FakeVcluster(fail=True)).reconcile([revision()], [])
  condition = last(store, "demo.reviews.1")
  assert condition["reason"] == "ApplyFailed"
  assert "connection refused" in condition["message"]


def test_older_open_revision_is_superseded():
  store = FakeStore()
  reconciler(store, FakeVcluster(deployment())).reconcile([revision(1), revision(2), revision(3, reason="Pending", status="Unknown")], [])
  assert last(store, "demo.reviews.1")["reason"] == "Superseded"
  assert last(store, "demo.reviews.2")["reason"] == "Superseded"
  assert last(store, "demo.reviews.3")["reason"] == "Succeeded"


def test_succeeded_revision_refreshes_the_instance_health():
  store = FakeStore()
  instance = {"metadata": {"name": "demo.reviews"}, "status": {"replicas": {"desired": 2, "ready": 2}, "conditions": [{"type": "Ready", "status": "True", "reason": "Available", "message": "2/2 replicas ready"}]}}
  done = revision(reason="Succeeded", status="True")
  reconciler(store, FakeVcluster(deployment(desired=2, available=2))).reconcile([done], [instance])
  assert store.instance_status == {}
  assert store.revision_status == {}
  reconciler(store, FakeVcluster(deployment(desired=2, available=1))).reconcile([done], [instance])
  status = store.instance_status["demo.reviews"][-1]
  assert status["replicas"] == {"desired": 2, "ready": 1}
  assert status["conditions"][0]["reason"] == "Degraded"


def test_rollback_applies_like_a_deploy():
  store, vcluster = FakeStore(), FakeVcluster(deployment())
  rollback = revision(3, action="rollback")
  rollback["spec"]["rollbackOf"] = 1
  reconciler(store, vcluster).reconcile([revision(1, reason="Succeeded", status="True"), rollback], [])
  assert last(store, "demo.reviews.3")["reason"] == "Succeeded"
  assert store.instance_status["demo.reviews"][-1]["revision"] == 3


def test_remove_deletes_from_the_vcluster_and_the_instance():
  store, vcluster = FakeStore(), FakeVcluster(deployment())
  instance = {"metadata": {"name": "demo.reviews"}, "status": {}}
  done = revision(1, reason="Succeeded", status="True")
  assert reconciler(store, vcluster).reconcile([done, revision(2, action="remove")], [instance]) is False
  assert vcluster.deleted == [("Service", "apps", "reviews"), ("Deployment", "apps", "reviews")]
  assert store.deleted_requests == [("demo", "reviews")]
  assert store.deleted_instances == ["demo.reviews"]
  assert (last(store, "demo.reviews.2")["status"], last(store, "demo.reviews.2")["reason"]) == ("True", "Succeeded")
  # A finished remove is left alone on the next passes.
  removed = revision(2, action="remove", reason="Succeeded", status="True")
  reconciler(store, vcluster).reconcile([done, removed], [])
  assert len(vcluster.deleted) == 2
  assert store.instance_status == {}


def test_remove_waits_for_the_environment():
  store, vcluster = FakeStore(environment_ready=False), FakeVcluster()
  assert reconciler(store, vcluster).reconcile([revision(1, action="remove")], []) is True
  assert last(store, "demo.reviews.1")["reason"] == "EnvironmentNotReady"
  assert vcluster.deleted == []


def test_remove_failed():
  store = FakeStore()
  reconciler(store, FakeVcluster(fail=True)).reconcile([revision(1, action="remove")], [])
  assert last(store, "demo.reviews.1")["reason"] == "ApplyFailed"
  assert store.deleted_instances == []


def with_db():
  spec = score(resources={"db": {"type": "postgres"}})
  spec["containers"]["api"]["variables"] = {"DB_HOST": "${resources.db.host}", "DB_PASSWORD": "${resources.db.password}"}
  return FakeStore(app_spec=spec)


def request(revision_number=1, resolved=("True", "Resolved", "db: postgres/provision"), ready=("True", "Ready", "postgres reviews-db ready in demo")):
  return {
    "metadata": {"name": "demo.reviews.db"},
    "spec": {"type": "postgres", "mode": "provision"},
    "status": {
      "revision": revision_number,
      "outputs": {"host": "reviews-db.apps"},
      "secretRef": {"name": "reviews-db", "keys": ["password"]},
      "conditions": [
        {"type": "Resolved", "status": resolved[0], "reason": resolved[1], "message": resolved[2]},
        {"type": "Ready", "status": ready[0], "reason": ready[1], "message": ready[2]},
      ],
    },
  }


@pytest.mark.parametrize("existing,message", [
  (None, "db: waiting for the Forager"),
  (request(revision_number=0), "db: waiting for the Forager"),
  (request(ready=("Unknown", "Provisioning", "waiting for postgres reviews-db")), "db: waiting for postgres reviews-db"),
])
def test_resources_pending(existing, message):
  store, vcluster = with_db(), FakeVcluster(deployment())
  if existing:
    store.requests["demo.reviews.db"] = existing
  assert reconciler(store, vcluster).reconcile([revision()], []) is True
  condition = last(store, "demo.reviews.1")
  assert (condition["status"], condition["reason"], condition["message"]) == ("Unknown", "ResourcesPending", message)
  assert vcluster.applied == []


@pytest.mark.parametrize("existing,reason,message", [
  (request(resolved=("False", "NoProviderForCapability", "db: no provisioner for postgres in demo")), "ResourcesNotSupported", "db: no provisioner for postgres in demo"),
  (request(resolved=("False", "ResourceModeChanged", "db is provision and ...")), "ResourceModeChanged", "db is provision and ..."),
  (request(ready=("False", "Failed", "invalid name")), "ResourcesFailed", "db: invalid name"),
])
def test_resources_end_the_revision(existing, reason, message):
  store, vcluster = with_db(), FakeVcluster(deployment())
  store.requests["demo.reviews.db"] = existing
  assert reconciler(store, vcluster).reconcile([revision()], []) is False
  condition = last(store, "demo.reviews.1")
  assert (condition["status"], condition["reason"], condition["message"]) == ("False", reason, message)
  assert vcluster.applied == []


def test_resources_ready_fill_the_deployment_and_the_instance():
  store, vcluster = with_db(), FakeVcluster(deployment())
  store.requests["demo.reviews.db"] = request()
  vcluster.objects = []
  original = vcluster.apply
  vcluster.apply = lambda obj, manager: (vcluster.objects.append(obj), original(obj, manager))
  reconciler(store, vcluster).reconcile([revision()], [])
  assert last(store, "demo.reviews.1")["reason"] == "Succeeded"
  env = vcluster.objects[1]["spec"]["template"]["spec"]["containers"][0]["env"]
  assert env == [{"name": "DB_HOST", "value": "reviews-db.apps"}, {"name": "DB_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "reviews-db", "key": "password"}}}]
  assert store.instance_status["demo.reviews"][-1]["resources"] == [{"name": "db", "type": "postgres", "mode": "provision", "status": "Ready"}]
