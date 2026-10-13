"""The golden signals of a Workload Instance (#411, ADR 0040), read on demand from the platform-local Prometheus.

Latency, traffic and errors come from the Istio sidecar of each pod (reporter="destination"), with the
vcluster-side names: destination_workload is the instance, in the namespace apps. The environment comes
from the host namespace, through the relabel of the job sidecars. Saturation is the highest of CPU and
memory usage over the container's limit, from cAdvisor, joined to the instance by pod with the up series
of the job sidecars; istio-proxy is left out. No CRD keeps a signal: each request queries Prometheus.
"""
import math
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException

from . import capabilities
from .auth import Principal, current_principal
from .environments import can_use
from .state import ENVIRONMENTS, NotFound
from .workloads import INSTANCES

CAPABILITY = "observability"
WINDOW = re.compile(r"([1-9][0-9]*)([mh])")
# Prometheus keeps 6h (platform/observability/deploy/prometheus.yaml): a longer window reads a partial one.
MAX_WINDOW_MINUTES = 6 * 60
# The containers saturation leaves out: the pod-level series, the pause container and the sidecar.
NOT_APP = 'container!~"|POD|istio-proxy"'
NO_REQUESTS = "no requests in window"
NO_LIMIT = "no CPU or memory limit declared"
NO_PODS = "no pods scraped in window"


class Unreachable(Exception):
  """Prometheus did not answer: 503, never a signal read as zero."""


class PrometheusQuery:
  """Instant queries over HTTP, inside the cluster."""

  def __init__(self, url: str, timeout: float = 10):
    self.http = httpx.Client(base_url=url, timeout=timeout)

  def scalar(self, promql: str) -> float | None:
    """The value of a query that yields at most one series; None when it yields none, or NaN."""
    try:
      response = self.http.get("/api/v1/query", params={"query": promql})
      response.raise_for_status()
    except httpx.HTTPError as error:
      raise Unreachable(f"prometheus: {error}") from error
    result = response.json()["data"]["result"]
    if not result:
      return None
    value = float(result[0]["value"][1])
    return None if math.isnan(value) or math.isinf(value) else value


def minutes(window: str) -> int:
  found = WINDOW.fullmatch(window)
  if not found:
    raise HTTPException(422, f"window '{window}': a number of minutes or hours, as 5m or 1h")
  total = int(found.group(1)) * (60 if found.group(2) == "h" else 1)
  if total > MAX_WINDOW_MINUTES:
    raise HTTPException(422, f"window '{window}': at most {MAX_WINDOW_MINUTES // 60}h, the retention of Prometheus")
  return total


def queries(environment: str, instance: str, window: str) -> dict[str, str]:
  requests = f'reporter="destination",environment="{environment}",destination_workload_namespace="apps",destination_workload="{instance}"'
  pods = f'up{{job="sidecars",environment="{environment}",workload_instance="{instance}"}}'
  containers = f'namespace="env-{environment}",{NOT_APP}'

  def usage_over_limit(usage: str, limit: str) -> str:
    # by (pod, container): cAdvisor repeats a container per cgroup id; and on (pod) keeps the instance's pods.
    return f"max((max by (pod, container) ({usage}) / {limit}) and on (pod) {pods})"

  return {
    "latency": f"histogram_quantile(0.95, sum by (le) (rate(istio_request_duration_milliseconds_bucket{{{requests}}}[{window}])))",
    "traffic": f"sum(rate(istio_requests_total{{{requests}}}[{window}]))",
    "errors": f'sum(rate(istio_requests_total{{{requests},response_code=~"5.."}}[{window}]))',
    "pods": f"count({pods})",
    "cpu": usage_over_limit(
      f"rate(container_cpu_usage_seconds_total{{{containers}}}[{window}])",
      # No quota series for a container without a CPU limit: the division yields nothing.
      f"(max by (pod, container) (container_spec_cpu_quota{{{containers}}}) / max by (pod, container) (container_spec_cpu_period{{{containers}}}))",
    ),
    "memory": usage_over_limit(
      f"container_memory_working_set_bytes{{{containers}}}",
      # A container without a memory limit reports 0.
      f"(max by (pod, container) (container_spec_memory_limit_bytes{{{containers}}}) > 0)",
    ),
  }


def rounded(value: float | None) -> float | None:
  return None if value is None else round(value, 4)


def read(prometheus, environment: str, instance: str, window: str) -> dict:
  found = {name: prometheus.scalar(promql) for name, promql in queries(environment, instance, window).items()}
  traffic = found["traffic"] or 0.0
  cpu, memory = found["cpu"], found["memory"]
  measured = [value for value in (cpu, memory) if value is not None]
  if measured:
    reason = None
  else:
    reason = NO_LIMIT if found["pods"] else NO_PODS
  return {
    "kind": "WorkloadSignals",
    "name": f"{instance}@{environment}",
    "environment": environment,
    "instance": instance,
    "window": window,
    "latencyP95Ms": rounded(found["latency"]) if traffic else None,
    "trafficRps": rounded(traffic),
    "errorRate": rounded((found["errors"] or 0.0) / traffic) if traffic else None,
    "saturation": {"value": rounded(max(measured)) if measured else None, "cpu": rounded(cpu), "memory": rounded(memory), "reason": reason},
    "message": None if traffic else NO_REQUESTS,
  }


def router(state, deployments, prometheus) -> APIRouter:
  routes = APIRouter(prefix="/v1/environments/{environment}/workloads/{instance}")

  @routes.get("/signals")
  def signals(environment: str, instance: str, window: str = "5m", principal: Principal = Depends(current_principal)):
    try:
      obj = state.get(ENVIRONMENTS, environment)
    except NotFound:
      raise HTTPException(404, f"environment '{environment}' not found")
    if not can_use(obj, principal):
      raise HTTPException(403, f"environment '{environment}' is not yours nor shared with your teams")
    minutes(window)
    kept = [item for item in state.list(INSTANCES) if item["spec"].get("environment") == environment and item["spec"].get("instance") == instance]
    if not kept:
      raise HTTPException(404, f"workload '{instance}' not found in environment '{environment}'")
    # A read, so requires() lets it through: without the Prometheus there is nothing to read.
    if deployments is not None and not capabilities.installed(deployments.list(), CAPABILITY):
      raise capabilities.NoProvider(CAPABILITY)
    if prometheus is None:
      raise capabilities.NoProvider(CAPABILITY)
    return read(prometheus, environment, instance, window)

  return routes
