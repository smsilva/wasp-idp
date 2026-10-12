import re

import pytest

from workload_provider.main import wakes
from workload_provider.routes import FINALIZER, RouteReconciler, accepted, baggage_pattern, render_route

from test_reconciler import NOW

SANDBOX = {"match": {"header": {"name": "x-sandbox", "value": "pr-42"}}, "to": "reviews-pr-42"}
BAGGAGE = {"match": {"baggage": {"key": "sandbox", "value": "pr-42"}}, "to": "reviews-pr-42"}
WEIGHTS = {"weights": {"reviews-pr-42": 10, "reviews": 90}}
PORTS = {"reviews": 9080, "reviews-pr-42": 9080}


def route(*rules, deleting=False, finalizers=(FINALIZER,), generation=2):
  metadata = {"name": "demo.reviews", "generation": generation, "resourceVersion": "7", "finalizers": list(finalizers)}
  if deleting:
    metadata["deletionTimestamp"] = "2026-10-12T12:00:00Z"
  return {"metadata": metadata, "spec": {"environment": "demo", "component": "reviews", "rules": list(rules)}}


def test_header_rule_then_the_default():
  httproute = render_route(route(SANDBOX), PORTS)
  assert (httproute["kind"], httproute["metadata"]["name"], httproute["metadata"]["namespace"]) == ("HTTPRoute", "reviews", "apps")
  assert httproute["spec"]["parentRefs"] == [{"group": "", "kind": "Service", "name": "reviews", "port": 9080}]
  assert httproute["spec"]["rules"] == [
    {"matches": [{"headers": [{"name": "x-sandbox", "value": "pr-42"}]}], "backendRefs": [{"name": "reviews-pr-42", "port": 9080}]},
    {"backendRefs": [{"name": "reviews", "port": 9080}]},
  ]


def test_weights_rule_takes_the_rest():
  rules = render_route(route(BAGGAGE, WEIGHTS), {"reviews": 9080, "reviews-pr-42": 8080})["spec"]["rules"]
  assert rules[0]["matches"][0]["headers"][0]["type"] == "RegularExpression"
  assert rules[0]["matches"][0]["headers"][0]["name"] == "baggage"
  assert rules[1:] == [{"backendRefs": [{"name": "reviews", "port": 9080, "weight": 90}, {"name": "reviews-pr-42", "port": 8080, "weight": 10}]}]


@pytest.mark.parametrize("header,matches", [
  ("sandbox=pr-42", True),
  ("userId=7,sandbox=pr-42", True),
  ("userId=7, sandbox = pr-42 ;ttl=5,other=1", True),
  ("sandbox=pr-421", False),
  ("xsandbox=pr-42", False),
  ("sandbox=pr-4", False),
  ("userId=sandbox=pr-42", False),
])
def test_baggage_pattern(header, matches):
  # Istio matches the whole header value (RE2 full match).
  assert bool(re.fullmatch(baggage_pattern("sandbox", "pr-42"), header)) is matches


def test_baggage_pattern_escapes():
  assert re.fullmatch(baggage_pattern("a.b", "1"), "a.b=1")
  assert not re.fullmatch(baggage_pattern("a.b", "1"), "axb=1")


@pytest.mark.parametrize("httproute,expected", [
  (None, ("Unknown", "Pending")),
  ({"status": {"parents": []}}, ("Unknown", "Pending")),
  ({"status": {"parents": [{"conditions": [{"type": "Accepted", "status": "True"}]}]}}, ("Unknown", "Pending")),
  ({"status": {"parents": [{"conditions": [{"type": "Accepted", "status": "True"}, {"type": "ResolvedRefs", "status": "True"}]}]}}, ("True", "Accepted")),
  ({"status": {"parents": [{"conditions": [{"type": "Accepted", "status": "True"}, {"type": "ResolvedRefs", "status": "False", "reason": "BackendNotFound", "message": "no svc"}]}]}}, ("False", "BackendNotFound")),
])
def test_accepted(httproute, expected):
  assert accepted(httproute)[:2] == expected


class FakeStore:
  def __init__(self, mesh=True, ready=True, deleting=False, kubeconfig=True):
    status = {"conditions": [{"type": "Ready", "status": "True" if ready else "False"}]}
    if kubeconfig:
      status["kubeconfigData"] = "kubeconfig"
    if mesh:
      status["mesh"] = {"istio": "1.30.0", "gatewayAPI": "v1.5.0"}
    self.environment = {"metadata": {"name": "demo"}, "status": status}
    if deleting:
      self.environment["metadata"]["deletionTimestamp"] = "2026-10-12T12:00:00Z"
    self.status, self.finalizers = [], []

  def get_environment(self, name):
    return self.environment

  def patch_route_status(self, name, status):
    self.status.append(status)

  def add_route_finalizer(self, route, finalizer):
    self.finalizers.append(("add", finalizer))
    route["metadata"]["finalizers"] = [*route["metadata"]["finalizers"], finalizer]

  def remove_route_finalizer(self, route, finalizer):
    self.finalizers.append(("remove", finalizer))


class FakeVcluster:
  def __init__(self, ports=PORTS, httproute=None, fail=False):
    self.ports, self.httproute, self.fail = ports, httproute, fail
    self.applied, self.deleted = [], []

  def service_port(self, namespace, name):
    return self.ports.get(name)

  def apply(self, obj, manager):
    if self.fail:
      raise RuntimeError("no matches for kind HTTPRoute")
    self.applied.append(obj)

  def get(self, api_version, kind, namespace, name):
    return self.httproute

  def delete(self, api_version, kind, namespace, name):
    self.deleted.append((kind, namespace, name))


class FakeVclusters:
  def __init__(self, vcluster):
    self.vcluster = vcluster

  def of(self, environment):
    return self.vcluster


ACCEPTED = {"status": {"parents": [{"conditions": [{"type": "Accepted", "status": "True"}, {"type": "ResolvedRefs", "status": "True"}]}]}}


def reconciler(store, vcluster):
  return RouteReconciler(store, FakeVclusters(vcluster), now=lambda: NOW)


def test_route_applied_and_accepted():
  store, vcluster = FakeStore(), FakeVcluster(httproute=ACCEPTED)
  assert reconciler(store, vcluster).reconcile([route(SANDBOX)]) is False
  assert [obj["metadata"]["name"] for obj in vcluster.applied] == ["reviews"]
  assert store.status[-1]["observedGeneration"] == 2
  assert store.status[-1]["conditions"][0]["reason"] == "Accepted"


def test_route_waits_for_the_mesh_to_accept():
  store, vcluster = FakeStore(), FakeVcluster()
  assert reconciler(store, vcluster).reconcile([route(SANDBOX)]) is True
  assert store.status[-1]["conditions"][0]["status"] == "Unknown"


def test_unchanged_status_is_not_written_again():
  store, vcluster = FakeStore(), FakeVcluster(httproute=ACCEPTED)
  obj = route(SANDBOX)
  obj["status"] = {"observedGeneration": 2, "conditions": [{"type": "Ready", "status": "True", "reason": "Accepted", "message": "the mesh routes the traffic"}]}
  reconciler(store, vcluster).reconcile([obj])
  assert store.status == []


def test_finalizer_added_once():
  store, vcluster = FakeStore(), FakeVcluster(httproute=ACCEPTED)
  reconciler(store, vcluster).reconcile([route(SANDBOX, finalizers=())])
  assert store.finalizers == [("add", FINALIZER)]


def test_environment_without_mesh():
  store, vcluster = FakeStore(mesh=False), FakeVcluster()
  assert reconciler(store, vcluster).reconcile([route(SANDBOX)]) is False
  assert store.status[-1]["conditions"][0]["reason"] == "MeshNotInstalled"
  assert vcluster.applied == []


def test_environment_not_ready():
  store, vcluster = FakeStore(ready=False), FakeVcluster()
  assert reconciler(store, vcluster).reconcile([route(SANDBOX)]) is True
  assert store.status[-1]["conditions"][0]["reason"] == "EnvironmentNotReady"


def test_instance_without_service_waits():
  store, vcluster = FakeStore(), FakeVcluster(ports={"reviews": 9080})
  assert reconciler(store, vcluster).reconcile([route(SANDBOX)]) is True
  assert store.status[-1]["conditions"][0]["reason"] == "InstancePending"
  assert vcluster.applied == []


def test_apply_failed():
  store, vcluster = FakeStore(), FakeVcluster(fail=True)
  assert reconciler(store, vcluster).reconcile([route(SANDBOX)]) is False
  assert store.status[-1]["conditions"][0]["reason"] == "ApplyFailed"


def test_delete_removes_the_httproute_then_the_finalizer():
  store, vcluster = FakeStore(), FakeVcluster()
  reconciler(store, vcluster).reconcile([route(SANDBOX, deleting=True)])
  assert vcluster.deleted == [("HTTPRoute", "apps", "reviews")]
  assert store.finalizers == [("remove", FINALIZER)]


@pytest.mark.parametrize("store", [FakeStore(deleting=True), FakeStore(kubeconfig=False)])
def test_delete_with_the_environment_going_leaves_the_vcluster_alone(store):
  vcluster = FakeVcluster()
  reconciler(store, vcluster).reconcile([route(SANDBOX, deleting=True)])
  assert vcluster.deleted == []
  assert store.finalizers == [("remove", FINALIZER)]


def test_wakes_on_spec_changes_only():
  seen = {}
  obj = {"metadata": {"name": "demo.reviews", "generation": 1}}
  assert wakes("ADDED", obj, seen)
  # A status write by the provider itself.
  assert not wakes("MODIFIED", obj, seen)
  assert wakes("MODIFIED", {"metadata": {"name": "demo.reviews", "generation": 2}}, seen)
  assert wakes("DELETED", obj, seen)
  assert seen == {}
