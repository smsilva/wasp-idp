from datetime import datetime, timezone

import pytest

from local_vcluster_provider.helm import values
from local_vcluster_provider.reconciler import FINALIZER, PORTS, RELEASE, Reconciler

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


class FakeStore:
  def __init__(self):
    self.finalizers, self.statuses, self.deleted, self.namespaces_deleted = {}, {}, [], []

  def set_finalizers(self, name, finalizers):
    self.finalizers[name] = finalizers

  def patch_status(self, name, status):
    self.statuses.setdefault(name, []).append(status)

  def delete(self, name):
    self.deleted.append(name)

  def delete_namespace(self, namespace):
    self.namespaces_deleted.append(namespace)


class FakeHelm:
  def __init__(self, fail=False):
    self.releases, self.fail = {}, fail

  def installed(self, release, namespace):
    return (release, namespace) in self.releases

  def install(self, release, namespace, port):
    if self.fail:
      raise RuntimeError("helm: chart not found")
    self.releases[(release, namespace)] = port

  def uninstall(self, release, namespace):
    self.releases.pop((release, namespace), None)


class FakeSecrets:
  def __init__(self, kubeconfigs=None, used=()):
    self.kubeconfigs, self.used = kubeconfigs or {}, set(used)

  def read(self, namespace, name):
    return self.kubeconfigs.get(namespace)

  def used_ports(self, selector):
    return self.used


def environment(name="greetings-test", expires=None, finalizers=None, deleting=False, status=None):
  obj = {"metadata": {"name": name, "finalizers": finalizers or []}, "spec": {"profile": "ephemeral"}}
  if expires:
    obj["spec"]["expiresAt"] = expires
  if deleting:
    obj["metadata"]["deletionTimestamp"] = "2026-10-10T11:00:00Z"
  if status:
    obj["status"] = status
  return obj


def build(helm=None, secrets=None):
  store = FakeStore()
  helm = helm or FakeHelm()
  secrets = secrets or FakeSecrets()
  return store, helm, secrets, Reconciler(store, helm, secrets, now=lambda: NOW)


def test_new_environment_installs_vcluster_on_first_free_port():
  store, helm, secrets, reconciler = build(secrets=FakeSecrets(used={7100}))
  reconciler.reconcile(environment())
  assert helm.releases == {(RELEASE, "env-greetings-test"): 7101}
  assert store.finalizers["greetings-test"] == [FINALIZER]
  last = store.statuses["greetings-test"][-1]
  assert last["port"] == 7101 and last["conditions"][0]["reason"] == "Provisioning"


def test_ready_once_the_kubeconfig_secret_exists():
  secrets = FakeSecrets(kubeconfigs={"env-greetings-test": "apiVersion: v1\nkind: Config\n"})
  store, helm, _, reconciler = build(secrets=secrets)
  reconciler.reconcile(environment(finalizers=[FINALIZER], status={"port": 7105}))
  last = store.statuses["greetings-test"][-1]
  assert last["conditions"][0]["status"] == "True"
  assert last["kubeconfigData"].startswith("apiVersion: v1")
  assert last["port"] == 7105
  assert helm.releases[(RELEASE, "env-greetings-test")] == 7105


def test_ready_environment_is_left_alone():
  kubeconfig = "apiVersion: v1\n"
  secrets = FakeSecrets(kubeconfigs={"env-greetings-test": kubeconfig})
  helm = FakeHelm()
  helm.releases[(RELEASE, "env-greetings-test")] = 7100
  store, _, _, reconciler = build(helm=helm, secrets=secrets)
  status = {"port": 7100, "kubeconfigData": kubeconfig, "conditions": [{"type": "Ready", "status": "True"}]}
  reconciler.reconcile(environment(finalizers=[FINALIZER], status=status))
  assert "greetings-test" not in store.statuses


def test_no_free_port_fails_with_condition():
  store, helm, _, reconciler = build(secrets=FakeSecrets(used=set(PORTS)))
  reconciler.reconcile(environment())
  last = store.statuses["greetings-test"][-1]["conditions"][0]
  assert last["reason"] == "ProvisioningFailed" and "7100-7119" in last["message"]
  assert not helm.releases


def test_helm_failure_becomes_condition():
  store, _, _, reconciler = build(helm=FakeHelm(fail=True))
  reconciler.reconcile(environment())
  assert store.statuses["greetings-test"][-1]["conditions"][0]["reason"] == "ProvisioningFailed"


def test_delete_uninstalls_and_removes_namespace_and_finalizer():
  helm = FakeHelm()
  helm.releases[(RELEASE, "env-gone")] = 7100
  store, _, _, reconciler = build(helm=helm)
  reconciler.reconcile(environment("gone", finalizers=[FINALIZER, "other"], deleting=True))
  assert not helm.releases
  assert store.namespaces_deleted == ["env-gone"]
  assert store.finalizers["gone"] == ["other"]


def test_expired_environment_is_deleted():
  store, helm, _, reconciler = build()
  reconciler.reconcile(environment(expires="2026-10-10T11:59:00Z", finalizers=[FINALIZER]))
  assert store.deleted == ["greetings-test"]
  assert not helm.releases


@pytest.mark.parametrize("port", [7100, 7119])
def test_values_expose_the_api_on_the_host_port(port):
  rendered = values(port)
  service = rendered["controlPlane"]["service"]["spec"]
  assert service["type"] == "LoadBalancer" and service["ports"][0]["port"] == port
  assert rendered["exportKubeConfig"]["server"] == f"https://127.0.0.1:{port}"
  assert "127.0.0.1" in rendered["controlPlane"]["proxy"]["extraSANs"]
