from datetime import datetime, timezone

import pytest
import yaml

from local_vcluster_provider.entrypoint import HOST_SERVICE, Entrypoint, gateway, ingress, programmed
from local_vcluster_provider.helm import values
from local_vcluster_provider.mesh import in_cluster, wanted
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


class FakeMesh:
  def __init__(self, ready=True):
    self.installs, self.is_ready = [], ready

  def install(self, name, kubeconfig):
    self.installs.append(name)

  def ready(self, name, kubeconfig):
    return self.is_ready


class FakeEntrypoint:
  def __init__(self, ready=True):
    self.installs, self.is_ready = [], ready

  def wanted(self, name):
    return Entrypoint().wanted(name)

  def install(self, name, kubeconfig, namespace):
    self.installs.append((name, namespace))

  def ready(self, name, kubeconfig):
    return self.is_ready


def environment(name="greetings-test", expires=None, finalizers=None, deleting=False, status=None):
  obj = {"metadata": {"name": name, "finalizers": finalizers or []}, "spec": {"profile": "ephemeral"}}
  if expires:
    obj["spec"]["expiresAt"] = expires
  if deleting:
    obj["metadata"]["deletionTimestamp"] = "2026-10-10T11:00:00Z"
  if status:
    obj["status"] = status
  return obj


def build(helm=None, secrets=None, mesh=None, entrypoint=None):
  store = FakeStore()
  helm = helm or FakeHelm()
  secrets = secrets or FakeSecrets()
  mesh = mesh or FakeMesh()
  entrypoint = entrypoint or FakeEntrypoint()
  return store, helm, secrets, Reconciler(store, helm, secrets, mesh, entrypoint, now=lambda: NOW)


INGRESS = {"domain": "greetings-test.localhost", "port": 7080}


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
  status = {"port": 7100, "kubeconfigData": kubeconfig, "mesh": wanted(), "ingress": INGRESS, "conditions": [{"type": "Ready", "status": "True"}]}
  reconciler.reconcile(environment(finalizers=[FINALIZER], status=status))
  assert "greetings-test" not in store.statuses


def test_mesh_installed_once_the_vcluster_is_up_and_ready_only_with_istiod():
  secrets = FakeSecrets(kubeconfigs={"env-greetings-test": "apiVersion: v1\n"})
  mesh = FakeMesh(ready=False)
  store, _, _, reconciler = build(secrets=secrets, mesh=mesh)
  reconciler.reconcile(environment(finalizers=[FINALIZER], status={"port": 7100}))
  assert mesh.installs == ["greetings-test"]
  statuses = store.statuses["greetings-test"]
  assert any("installing the mesh" in status["conditions"][0]["message"] for status in statuses if "conditions" in status)
  assert {"mesh": wanted()} in statuses
  last = statuses[-1]["conditions"][0]
  assert (last["status"], last["reason"], last["message"]) == ("False", "Provisioning", "waiting for istiod in the vcluster")


def test_mesh_not_reinstalled_while_istiod_starts():
  secrets = FakeSecrets(kubeconfigs={"env-greetings-test": "apiVersion: v1\n"})
  mesh = FakeMesh()
  store, _, _, reconciler = build(secrets=secrets, mesh=mesh)
  reconciler.reconcile(environment(finalizers=[FINALIZER], status={"port": 7100, "mesh": wanted()}))
  assert mesh.installs == []
  last = store.statuses["greetings-test"][-1]
  assert last["conditions"][0]["reason"] == "ClusterReady" and last["mesh"] == wanted()


def test_environment_ready_before_the_mesh_gets_it():
  # Created before ADR 0035: Ready, with the kubeconfig, but no status.mesh.
  kubeconfig = "apiVersion: v1\n"
  helm = FakeHelm()
  helm.releases[(RELEASE, "env-greetings-test")] = 7100
  mesh = FakeMesh()
  store, _, _, reconciler = build(helm=helm, secrets=FakeSecrets(kubeconfigs={"env-greetings-test": kubeconfig}), mesh=mesh)
  status = {"port": 7100, "kubeconfigData": kubeconfig, "conditions": [{"type": "Ready", "status": "True"}]}
  reconciler.reconcile(environment(finalizers=[FINALIZER], status=status))
  assert mesh.installs == ["greetings-test"]
  assert store.statuses["greetings-test"][-1]["conditions"][0]["reason"] == "ClusterReady"


def test_mesh_failure_becomes_condition():
  class Failing(FakeMesh):
    def install(self, name, kubeconfig):
      raise RuntimeError("helm: istiod failed")
  store, _, _, reconciler = build(secrets=FakeSecrets(kubeconfigs={"env-greetings-test": "apiVersion: v1\n"}), mesh=Failing())
  reconciler.reconcile(environment(finalizers=[FINALIZER], status={"port": 7100}))
  last = store.statuses["greetings-test"][-1]["conditions"][0]
  assert last["reason"] == "ProvisioningFailed" and "istiod failed" in last["message"]


def test_mesh_reaches_the_vcluster_at_its_in_cluster_address():
  kubeconfig = yaml.safe_dump({"clusters": [{"name": "c", "cluster": {"server": "https://127.0.0.1:7100"}}]})
  assert in_cluster(kubeconfig, "greetings-test")["clusters"][0]["cluster"]["server"] == "https://vcluster.env-greetings-test"


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
  # The chart's Service keeps its default (ClusterIP, 443): the pods reach the API there (#307).
  assert "service" not in rendered["controlPlane"]
  service = yaml.safe_load(rendered["experimental"]["deploy"]["host"]["manifests"])
  assert service["metadata"]["labels"]["app"] == "vcluster"
  assert service["spec"]["type"] == "LoadBalancer" and service["spec"]["ports"][0] == {"name": "https", "port": port, "targetPort": 8443, "protocol": "TCP"}
  assert service["spec"]["selector"] == {"app": "vcluster", "release": "vcluster"}
  assert rendered["exportKubeConfig"]["server"] == f"https://127.0.0.1:{port}"
  assert "127.0.0.1" in rendered["controlPlane"]["proxy"]["extraSANs"]


def test_values_replicate_the_shared_instances_into_namespace_resources():
  # The pods of an environment reach shared-pg.resources, the host Service compose writes into (#305).
  assert values(7100)["networking"]["replicateServices"] == {"fromHost": [{"from": "platform-resources/shared-pg", "to": "resources/shared-pg"}]}


def test_gateway_created_after_istiod_and_ready_only_once_programmed():
  entrypoint = FakeEntrypoint(ready=False)
  store, _, _, reconciler = build(secrets=FakeSecrets(kubeconfigs={"env-greetings-test": "apiVersion: v1\n"}), entrypoint=entrypoint)
  reconciler.reconcile(environment(finalizers=[FINALIZER], status={"port": 7100, "mesh": wanted()}))
  assert entrypoint.installs == [("greetings-test", "env-greetings-test")]
  statuses = store.statuses["greetings-test"]
  assert {"ingress": INGRESS} in statuses
  last = statuses[-1]["conditions"][0]
  assert (last["status"], last["message"]) == ("False", "waiting for the gateway in the vcluster")


def test_gateway_waits_for_istiod():
  entrypoint = FakeEntrypoint()
  store, _, _, reconciler = build(secrets=FakeSecrets(kubeconfigs={"env-greetings-test": "apiVersion: v1\n"}), mesh=FakeMesh(ready=False), entrypoint=entrypoint)
  reconciler.reconcile(environment(finalizers=[FINALIZER], status={"port": 7100, "mesh": wanted()}))
  assert entrypoint.installs == []


def test_ready_environment_tells_where_its_workloads_are():
  entrypoint = FakeEntrypoint()
  store, _, _, reconciler = build(secrets=FakeSecrets(kubeconfigs={"env-greetings-test": "apiVersion: v1\n"}), entrypoint=entrypoint)
  reconciler.reconcile(environment(finalizers=[FINALIZER], status={"port": 7100, "mesh": wanted(), "ingress": INGRESS}))
  assert entrypoint.installs == []
  last = store.statuses["greetings-test"][-1]
  assert last["ingress"] == INGRESS
  assert "workloads on http://*.greetings-test.localhost:7080" in last["conditions"][0]["message"]


def test_environment_ready_before_the_gateway_gets_it():
  # Created before ADR 0036: Ready, with the mesh, but no status.ingress.
  kubeconfig = "apiVersion: v1\n"
  entrypoint = FakeEntrypoint()
  store, _, _, reconciler = build(secrets=FakeSecrets(kubeconfigs={"env-greetings-test": kubeconfig}), entrypoint=entrypoint)
  status = {"port": 7100, "kubeconfigData": kubeconfig, "mesh": wanted(), "conditions": [{"type": "Ready", "status": "True"}]}
  reconciler.reconcile(environment(finalizers=[FINALIZER], status=status))
  assert entrypoint.installs == [("greetings-test", "env-greetings-test")]
  assert store.statuses["greetings-test"][-1]["conditions"][0]["reason"] == "ClusterReady"


def test_gateway_takes_the_hosts_of_its_environment_only():
  namespace, obj = gateway("greetings-test")
  assert namespace["metadata"]["name"] == obj["metadata"]["namespace"] == "istio-ingress"
  assert obj["metadata"]["annotations"]["networking.istio.io/service-type"] == "ClusterIP"
  listener = obj["spec"]["listeners"][0]
  assert listener["hostname"] == "*.greetings-test.localhost"
  assert listener["allowedRoutes"] == {"namespaces": {"from": "All"}}


def test_ingress_sends_the_hosts_of_the_environment_to_its_gateway():
  obj = ingress("greetings-test", "env-greetings-test")
  assert obj["metadata"]["namespace"] == "env-greetings-test"
  assert obj["spec"]["ingressClassName"] == "platform"
  rule = obj["spec"]["rules"][0]
  assert rule["host"] == "*.greetings-test.localhost"
  assert rule["http"]["paths"][0]["backend"]["service"] == {"name": HOST_SERVICE, "port": {"number": 80}}
  assert HOST_SERVICE == "platform-istio-x-istio-ingress-x-vcluster"


def test_gateway_is_ready_only_when_programmed():
  assert not programmed(None)
  assert not programmed({"status": {"conditions": [{"type": "Accepted", "status": "True"}, {"type": "Programmed", "status": "False"}]}})
  assert programmed({"status": {"conditions": [{"type": "Programmed", "status": "True"}]}})
