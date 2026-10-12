import pytest

from forager_provider.postgres import OWNER, InvalidName, object_name
from forager_provider.routing import GATEWAY_API, Dns, Route, accepted
from test_postgres import FakeSecrets

ENVIRONMENT = {"metadata": {"name": "demo"}, "status": {"ingress": {"domain": "demo.localhost", "port": 7080}}}


def request(resource="route"):
  return {"metadata": {"name": f"demo.reviews.{resource}"}, "spec": {"environment": "demo", "instance": "reviews", "component": "reviews", "resource": resource, "type": resource}}


NAME = object_name(request())


class FakeVcluster:
  def __init__(self, accepted=None, existing=None):
    self.applied, self.deleted, self.accepted, self.existing = [], [], accepted, existing

  def apply(self, obj, manager):
    self.applied.append(obj)

  def get(self, api_version, kind, namespace, name):
    if self.existing is not None:
      return self.existing
    if not any(obj["kind"] == "HTTPRoute" for obj in self.applied):
      return None
    route = {"metadata": {"annotations": {OWNER: "demo.reviews.route"}}}
    if self.accepted is not None:
      route["status"] = {"parents": [{"parentRef": {"name": "platform"}, "conditions": [{"type": "Accepted", "status": self.accepted[0], "message": self.accepted[1]}]}]}
    return route

  def delete(self, api_version, kind, namespace, name):
    self.deleted.append((kind, namespace, name))


def environments(name):
  return ENVIRONMENT if name == "demo" else None


PARAMS = {"host": "reviews.demo.localhost", "path": "/", "port": "80"}


def test_dns_gives_the_instance_a_host_under_its_environment():
  assert Dns(environments).ensure(request("dns"), {}, None, FakeSecrets()) == ("Ready", "reviews.demo.localhost", {"host": "reviews.demo.localhost"}, None)


def test_without_an_entry_point_the_environment_is_too_old():
  with pytest.raises(InvalidName, match="no entry point"):
    Dns(lambda name: {"metadata": {"name": "demo"}, "status": {}}).ensure(request("dns"), {}, None, FakeSecrets())


def test_route_attaches_the_instance_to_the_gateway_of_its_environment():
  vcluster = FakeVcluster(accepted=("True", "Accepted"))
  state, message, outputs, secret_ref = Route(environments).ensure(request(), PARAMS, vcluster, FakeSecrets())
  assert (state, secret_ref) == ("Ready", None)
  assert outputs == {"host": "reviews.demo.localhost", "path": "/", "url": "http://reviews.demo.localhost:7080/"}
  assert message == "http://reviews.demo.localhost:7080/ routed to reviews:80"
  route = vcluster.applied[-1]
  assert route["metadata"]["name"] == NAME and route["metadata"]["namespace"] == "apps"
  assert route["metadata"]["annotations"][OWNER] == "demo.reviews.route"
  assert route["spec"]["parentRefs"] == [{"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": "platform", "namespace": "istio-ingress"}]
  assert route["spec"]["hostnames"] == ["reviews.demo.localhost"]
  assert route["spec"]["rules"] == [{"matches": [{"path": {"type": "PathPrefix", "value": "/"}}], "backendRefs": [{"name": "reviews", "port": 80}]}]


def test_route_waits_for_the_gateway_and_fails_when_refused():
  assert Route(environments).ensure(request(), PARAMS, FakeVcluster(), FakeSecrets())[0] == "Provisioning"
  state, message, _, _ = Route(environments).ensure(request(), PARAMS, FakeVcluster(accepted=("False", "no matching listener")), FakeSecrets())
  assert state == "Failed" and "no matching listener" in message


@pytest.mark.parametrize("params,error", [
  ({**PARAMS, "host": "other.demo.localhost"}, "params.host reviews.demo.localhost"),
  ({**PARAMS, "host": "reviews.prod.localhost"}, "params.host"),
  ({**PARAMS, "host": "evil.com"}, "params.host"),
  ({**PARAMS, "path": "no-slash"}, "params.path"),
  ({**PARAMS, "path": "/a b"}, "params.path"),
  ({**PARAMS, "port": "0"}, "params.port"),
  ({"host": "reviews.demo.localhost"}, "params.port"),
])
def test_route_params_are_checked(params, error):
  with pytest.raises(InvalidName, match=error):
    Route(environments).ensure(request(), params, FakeVcluster(), FakeSecrets())


def test_a_name_under_the_instance_host_is_its_own():
  outputs = Route(environments).ensure(request(), {**PARAMS, "host": "api.reviews.demo.localhost", "path": "/v1"}, FakeVcluster(accepted=("True", "")), FakeSecrets())[2]
  assert outputs["url"] == "http://api.reviews.demo.localhost:7080/v1"


def test_a_route_of_someone_else_is_refused():
  vcluster = FakeVcluster(existing={"metadata": {"annotations": {OWNER: "demo.other.route"}}})
  with pytest.raises(InvalidName, match="belongs to something else"):
    Route(environments).ensure(request(), PARAMS, vcluster, FakeSecrets())
  assert vcluster.applied == []


def test_delete_removes_only_its_own_route():
  vcluster = FakeVcluster(existing={"metadata": {"annotations": {OWNER: "demo.reviews.route"}}})
  Route(environments).delete(request(), vcluster, FakeSecrets())
  assert vcluster.deleted == [("HTTPRoute", "apps", NAME)]
  other = FakeVcluster(existing={"metadata": {"annotations": {OWNER: "demo.other.route"}}})
  Route(environments).delete(request(), other, FakeSecrets())
  Route(environments).delete(request(), None, FakeSecrets())
  assert other.deleted == []


def test_accepted_reads_the_condition_of_the_platform_gateway():
  assert accepted(None) == (None, "")
  other = {"status": {"parents": [{"parentRef": {"name": "mesh"}, "conditions": [{"type": "Accepted", "status": "True"}]}]}}
  assert accepted(other) == (None, "")
