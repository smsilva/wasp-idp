"""workload signals (#411, ADR 0040): the golden signals of an instance, read from Prometheus on demand."""
import httpx
import pytest
from fastapi.testclient import TestClient

from fakes import CATALOG_TEAMS, FakeTeams
from platform_api import signals
from platform_api.app import create_app
from platform_api.journal import Journal
from test_capabilities import FakeDeployments, deployment
from test_workloads import admin, instance, journal_path, owner, state, teammate, tokens  # noqa: F401

SIGNALS = "/v1/environments/demo/workloads/greeting-api/signals"


class FakePrometheus:
  """Answers each query by the name queries() gives it; a name left out yields no series."""

  def __init__(self, **values):
    self.values = values
    self.asked = []

  def scalar(self, promql):
    self.asked.append(promql)
    names = {query: name for name, query in signals.queries("demo", "greeting-api", self.window(promql)).items()}
    return self.values.get(names[promql])

  @staticmethod
  def window(promql):
    return promql.split("[", 1)[1].split("]", 1)[0] if "[" in promql else "5m"


@pytest.fixture
def prometheus():
  return FakePrometheus(latency=42.31, traffic=3.0, errors=0.06, pods=2, cpu=0.12, memory=0.31)


@pytest.fixture
def client(state, journal_path, tokens, prometheus):  # noqa: F811
  instance(state)
  return TestClient(create_app(
    state, Journal(journal_path), tokens.verifier(), teams=FakeTeams(*CATALOG_TEAMS),
    deployments=FakeDeployments([deployment("prometheus", "observability")]), prometheus=prometheus,
  ))


def test_the_four_signals(client, teammate):  # noqa: F811
  body = client.get(SIGNALS, headers=teammate).json()
  assert body["name"] == "greeting-api@demo"
  assert body["window"] == "5m"
  assert (body["latencyP95Ms"], body["trafficRps"], body["errorRate"]) == (42.31, 3.0, 0.02)
  assert body["saturation"] == {"value": 0.31, "cpu": 0.12, "memory": 0.31, "reason": None}
  assert body["message"] is None


def test_the_window_reaches_every_rate(client, owner, prometheus):  # noqa: F811
  client.get(SIGNALS, params={"window": "1h"}, headers=owner)
  assert all("[1h]" in promql for promql in prometheus.asked if "rate(" in promql)


def test_queries_select_the_instance_without_the_sidecar():
  found = signals.queries("demo", "greeting-api", "5m")
  assert 'reporter="destination",environment="demo",destination_workload_namespace="apps",destination_workload="greeting-api"' in found["traffic"]
  assert 'up{job="sidecars",environment="demo",workload_instance="greeting-api"}' in found["cpu"]
  for name in ("cpu", "memory"):
    assert 'namespace="env-demo",container!~"|POD|istio-proxy"' in found[name]


def test_no_requests_leaves_latency_and_errors_empty(client, owner, prometheus):  # noqa: F811
  prometheus.values.update(traffic=None, errors=None, latency=None)
  body = client.get(SIGNALS, headers=owner).json()
  assert (body["latencyP95Ms"], body["trafficRps"], body["errorRate"]) == (None, 0.0, None)
  assert body["message"] == "no requests in window"


def test_no_errors_is_zero(client, owner, prometheus):  # noqa: F811
  prometheus.values.update(errors=None)
  assert client.get(SIGNALS, headers=owner).json()["errorRate"] == 0.0


def test_saturation_without_a_limit(client, owner, prometheus):  # noqa: F811
  prometheus.values.update(cpu=None, memory=None)
  assert client.get(SIGNALS, headers=owner).json()["saturation"] == {"value": None, "cpu": None, "memory": None, "reason": "no CPU or memory limit declared"}
  prometheus.values.update(pods=None)
  assert client.get(SIGNALS, headers=owner).json()["saturation"]["reason"] == "no pods scraped in window"


def test_saturation_with_one_limit(client, owner, prometheus):  # noqa: F811
  prometheus.values.update(cpu=None)
  assert client.get(SIGNALS, headers=owner).json()["saturation"] == {"value": 0.31, "cpu": None, "memory": 0.31, "reason": None}


@pytest.mark.parametrize("window", ["5", "0m", "5s", "1d", "7h", "5m\n", "-5m"])
def test_window_refused(client, owner, window):  # noqa: F811
  assert client.get(SIGNALS, params={"window": window}, headers=owner).status_code == 422


def test_refusals(client, owner, tokens):  # noqa: F811
  assert client.get("/v1/environments/private/workloads/greeting-api/signals", headers=owner).status_code == 403
  assert client.get("/v1/environments/nowhere/workloads/greeting-api/signals", headers=owner).status_code == 404
  assert client.get("/v1/environments/demo/workloads/other/signals", headers=owner).status_code == 404
  assert client.get(SIGNALS).status_code == 401


def test_without_prometheus_is_no_provider(state, journal_path, tokens, owner):  # noqa: F811
  instance(state)
  client = TestClient(create_app(
    state, Journal(journal_path), tokens.verifier(), deployments=FakeDeployments([deployment("workload", "workload")]), prometheus=FakePrometheus(),
  ))
  response = client.get(SIGNALS, headers=owner)
  assert response.status_code == 503
  assert response.json()["error"]["code"] == "NoProviderForCapability"


def test_prometheus_down_is_unreachable(state, journal_path, tokens, owner):  # noqa: F811
  instance(state)
  down = signals.PrometheusQuery("http://prometheus.invalid:9090")
  down.http = httpx.Client(base_url="http://prometheus.invalid:9090", transport=httpx.MockTransport(lambda request: httpx.Response(502)))
  client = TestClient(create_app(
    state, Journal(journal_path), tokens.verifier(), deployments=FakeDeployments([deployment("prometheus", "observability")]), prometheus=down,
  ))
  response = client.get(SIGNALS, headers=owner)
  assert response.status_code == 503
  assert response.json()["error"]["code"] == "Unreachable"


def test_prometheus_query_reads_one_value():
  def answer(request):
    value = {"up": "1", "nan": "NaN"}.get(request.url.params["query"])
    result = [{"metric": {}, "value": [0, value]}] if value else []
    return httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": result}})

  prometheus = signals.PrometheusQuery("http://prometheus")
  prometheus.http = httpx.Client(base_url="http://prometheus", transport=httpx.MockTransport(answer))
  assert prometheus.scalar("up") == 1.0
  assert prometheus.scalar("nan") is None
  assert prometheus.scalar("absent") is None
