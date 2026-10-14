import httpx
import pytest
from mcp import Client
from wasp_platform.client import PlatformClient

from wasp_platform_mcp import server as mcp_server

INSTANCE = {"instance": "hello-api", "component": "hello-api", "environment": "demo", "version": "0.1.0-greetings.b5f9569", "status": "Running"}
REVISION = {"environment": "demo", "instance": "hello-api", "revision": 1, "status": "Succeeded", "open": False}
SIGNALS = {"latency": {"p95": 0.47}, "traffic": 0.98, "errors": 0.0, "saturation": 0.1063, "window": "5m"}

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
  return "asyncio"


def client_for(handler):
  return lambda: PlatformClient(base_url="http://api", transport=httpx.MockTransport(handler), token=lambda: "t")


def no_calls(request):
  raise AssertionError(f"unexpected call to {request.method} {request.url.path}")


async def call(tool: str, arguments: dict, handler=no_calls):
  async with Client(mcp_server.build(["workloads"], client=client_for(handler))) as client:
    return await client.call_tool(tool, arguments)


async def test_read_only_tools():
  async with Client(mcp_server.build(["workloads"], client=client_for(no_calls))) as client:
    tools = (await client.list_tools()).tools
  assert sorted(tool.name for tool in tools) == ["workloads_get", "workloads_history", "workloads_list", "workloads_signals"]
  assert all(tool.annotations.read_only_hint for tool in tools)


async def test_list_reads_the_environment():
  def handler(request):
    assert request.url.path == "/v1/environments/demo/workloads"
    return httpx.Response(200, json={"items": [INSTANCE]})

  result = await call("workloads_list", {"environment": "demo"}, handler)
  assert result.structured_content == {"items": [INSTANCE]}


async def test_get_reads_one_instance():
  def handler(request):
    assert request.url.path == "/v1/environments/demo/workloads/hello-api"
    return httpx.Response(200, json=INSTANCE)

  result = await call("workloads_get", {"environment": "demo", "instance": "hello-api"}, handler)
  assert result.structured_content == INSTANCE


async def test_history_filters_by_instance():
  def handler(request):
    assert request.url.path == "/v1/environments/demo/revisions"
    assert request.url.params.get("instance") == "hello-api"
    return httpx.Response(200, json={"items": [REVISION]})

  result = await call("workloads_history", {"environment": "demo", "instance": "hello-api"}, handler)
  assert result.structured_content == {"items": [REVISION]}


async def test_signals_default_window():
  def handler(request):
    assert request.url.path == "/v1/environments/demo/workloads/hello-api/signals"
    assert request.url.params.get("window") == "5m"
    return httpx.Response(200, json=SIGNALS)

  result = await call("workloads_signals", {"environment": "demo", "instance": "hello-api"}, handler)
  assert result.structured_content == SIGNALS


@pytest.mark.parametrize("arguments", [
  {"environment": "../catalog", "instance": "hello-api"},
  {"environment": "demo", "instance": "hello-api/signals"},
])
async def test_get_refuses_names_that_are_paths(arguments):
  result = await call("workloads_get", arguments)
  assert result.is_error
  assert "is not a platform name" in result.content[0].text
