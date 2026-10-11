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
    self.revision_status, self.instances, self.instance_status = {}, {}, {}

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


def deployment(desired=1, available=1, ready=None, generation=2, observed=2, deadline=False):
  conditions = [{"type": "Progressing", "reason": "ProgressDeadlineExceeded", "message": "exceeded its progress deadline"}] if deadline else []
  return {
    "metadata": {"generation": generation},
    "spec": {"replicas": desired},
    "status": {"observedGeneration": observed, "replicas": desired, "updatedReplicas": desired, "availableReplicas": available, "readyReplicas": available if ready is None else ready, "conditions": conditions},
  }


class FakeVcluster:
  def __init__(self, state=None, fail=False):
    self.applied, self.state, self.fail = [], state, fail

  def apply(self, obj, manager):
    if self.fail:
      raise RuntimeError("connection refused")
    self.applied.append((obj["kind"], obj["metadata"]["name"]))

  def deployment(self, namespace, name):
    return self.state


class FakeVclusters:
  def __init__(self, vcluster):
    self.vcluster = vcluster

  def of(self, environment):
    return self.vcluster


def revision(number=1, version="2.1.0", reason=None, status=None):
  obj = {"metadata": {"name": f"demo.reviews.{number}"}, "spec": {
    "environment": "demo", "instance": "reviews", "component": "reviews", "revision": number, "action": "deploy",
    "version": version, "image": "ghcr.io/acme/reviews", "digest": DIGEST,
  }}
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
  (FakeStore(app_spec=score(resources={"db": {"type": "postgres"}})), "2.1.0", "ResourcesNotSupported"),
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
