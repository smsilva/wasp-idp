from datetime import datetime, timezone
from pathlib import Path

from local_k3d_provider.reconciler import FINALIZER, Reconciler

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


class FakeStore:
  def __init__(self):
    self.finalizers = {}
    self.statuses = {}
    self.deleted = []

  def set_finalizers(self, name, finalizers):
    self.finalizers[name] = finalizers

  def patch_status(self, name, status):
    self.statuses.setdefault(name, []).append(status)

  def delete(self, name):
    self.deleted.append(name)


class FakeK3d:
  def __init__(self, clusters=(), fail=False):
    self.clusters = set(clusters)
    self.fail = fail

  def exists(self, cluster):
    return cluster in self.clusters

  def create(self, cluster):
    if self.fail:
      raise RuntimeError("docker is not running")
    self.clusters.add(cluster)

  def delete(self, cluster):
    self.clusters.discard(cluster)

  def write_kubeconfig(self, cluster, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cluster)


def environment(name="greetings-test", expires=None, finalizers=None, deleting=False, status=None):
  obj = {"metadata": {"name": name, "finalizers": finalizers or []}, "spec": {"profile": "ephemeral"}}
  if expires:
    obj["spec"]["expiresAt"] = expires
  if deleting:
    obj["metadata"]["deletionTimestamp"] = "2026-10-10T11:00:00Z"
  if status:
    obj["status"] = status
  return obj


def reconciler(tmp_path, k3d):
  store = FakeStore()
  return store, Reconciler(store, k3d, tmp_path, now=lambda: NOW)


def test_new_environment_gets_cluster_finalizer_and_ready(tmp_path):
  k3d = FakeK3d()
  store, rec = reconciler(tmp_path, k3d)
  rec.reconcile(environment(status={"conditions": [{"type": "Ready", "status": "False", "reason": "NoProviderForCapability"}]}))
  assert "env-greetings-test" in k3d.clusters
  assert store.finalizers["greetings-test"] == [FINALIZER]
  provisioning, ready = store.statuses["greetings-test"]
  assert provisioning["conditions"][0]["reason"] == "Provisioning"
  assert ready["conditions"][0]["status"] == "True"
  assert ready["kubeconfig"] == str(tmp_path / "greetings-test.kubeconfig")
  assert (tmp_path / "greetings-test.kubeconfig").exists()


def test_ready_environment_is_a_no_op(tmp_path):
  kubeconfig = tmp_path / "greetings-test.kubeconfig"
  kubeconfig.write_text("x")
  store, rec = reconciler(tmp_path, FakeK3d(["env-greetings-test"]))
  rec.reconcile(environment(
    finalizers=[FINALIZER],
    status={"kubeconfig": str(kubeconfig), "conditions": [{"type": "Ready", "status": "True"}]},
  ))
  assert store.statuses == {} and store.finalizers == {}


def test_deleting_environment_removes_cluster_then_finalizer(tmp_path):
  k3d = FakeK3d(["env-greetings-test"])
  (tmp_path / "greetings-test.kubeconfig").write_text("x")
  store, rec = reconciler(tmp_path, k3d)
  rec.reconcile(environment(finalizers=["other", FINALIZER], deleting=True))
  assert k3d.clusters == set()
  assert store.finalizers["greetings-test"] == ["other"]
  assert not (tmp_path / "greetings-test.kubeconfig").exists()


def test_deleting_environment_without_our_finalizer_is_ignored(tmp_path):
  k3d = FakeK3d(["env-greetings-test"])
  store, rec = reconciler(tmp_path, k3d)
  rec.reconcile(environment(deleting=True))
  assert k3d.clusters == {"env-greetings-test"} and store.finalizers == {}


def test_expired_environment_is_deleted(tmp_path):
  k3d = FakeK3d(["env-greetings-test"])
  store, rec = reconciler(tmp_path, k3d)
  rec.reconcile(environment(expires="2026-10-10T11:59:59Z", finalizers=[FINALIZER]))
  assert store.deleted == ["greetings-test"]
  assert k3d.clusters == {"env-greetings-test"}  # the cluster goes when the finalizer runs


def test_not_yet_expired_environment_is_kept(tmp_path):
  store, rec = reconciler(tmp_path, FakeK3d())
  rec.reconcile(environment(expires="2026-10-10T13:00:00Z"))
  assert store.deleted == []


def test_failure_becomes_condition(tmp_path):
  store, rec = reconciler(tmp_path, FakeK3d(fail=True))
  rec.reconcile(environment())
  last = store.statuses["greetings-test"][-1]["conditions"][0]
  assert (last["status"], last["reason"]) == ("False", "ProvisioningFailed")
  assert "docker is not running" in last["message"]
