import httpx
import pytest
from mcp import Client
from wasp_platform.client import PlatformClient

from wasp_platform_mcp import server as mcp_server
from wasp_platform_mcp.toolsets import TOOLSETS, ToolSpec

ME = {"sub": "u-1", "email": "dev@example.com", "groups": ["/platform-users"], "teams": []}

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
  return "asyncio"


def client_for(handler):
  return lambda: PlatformClient(base_url="http://api", transport=httpx.MockTransport(handler), token=lambda: "t")


def me_handler(request: httpx.Request) -> httpx.Response:
  assert request.url.path == "/v1/me"
  assert request.headers["Authorization"] == "Bearer t"
  return httpx.Response(200, json=ME)


async def test_core_lists_whoami_and_status_as_read_only():
  async with Client(mcp_server.build(["core"], client=client_for(me_handler))) as client:
    tools = (await client.list_tools()).tools
  assert sorted(tool.name for tool in tools) == ["status", "whoami"]
  assert all(tool.annotations.read_only_hint for tool in tools)


async def test_whoami_calls_v1_me():
  async with Client(mcp_server.build(["core"], client=client_for(me_handler))) as client:
    result = await client.call_tool("whoami", {})
  assert not result.is_error
  assert result.structured_content == ME


async def test_api_error_becomes_tool_error():
  def unauthorized(request):
    return httpx.Response(401)

  async with Client(mcp_server.build(["core"], client=client_for(unauthorized))) as client:
    result = await client.call_tool("whoami", {})
  assert result.is_error
  assert "platform login" in result.content[0].text


def test_unknown_toolset_fails_with_the_available_ones():
  with pytest.raises(ValueError, match="unknown toolset.*nope.*available: core"):
    mcp_server.build(["core", "nope"])


async def test_write_tools_need_allow_writes(monkeypatch):
  def change() -> str:
    """A write tool."""
    return "changed"

  monkeypatch.setitem(TOOLSETS, "test", lambda client: [ToolSpec("change", change, write=True, destructive=True)])

  async with Client(mcp_server.build(["test"])) as client:
    assert (await client.list_tools()).tools == []

  async with Client(mcp_server.build(["test"], allow_writes=True)) as client:
    tools = (await client.list_tools()).tools
  assert tools[0].annotations.read_only_hint is False
  assert tools[0].annotations.destructive_hint is True


CAPABILITIES = [{"name": "identity", "status": "Active"}, {"name": "build", "status": "NotInstalled"}]


async def test_core_status_lists_the_capabilities():
  def handler(request):
    assert request.url.path == "/v1/capabilities"
    return httpx.Response(200, json={"items": CAPABILITIES})

  async with Client(mcp_server.build(["core"], client=client_for(handler))) as client:
    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    result = await client.call_tool("status", {})
  assert tools["status"].annotations.read_only_hint is True
  assert result.structured_content == {"items": CAPABILITIES}


async def test_core_status_of_one_capability():
  def handler(request):
    assert request.url.path == "/v1/capabilities/cloud-account"
    return httpx.Response(200, json={"name": "cloud-account", "status": "Active"})

  async with Client(mcp_server.build(["core"], client=client_for(handler))) as client:
    result = await client.call_tool("status", {"capability": "cloud-account"})
  assert result.structured_content == {"name": "cloud-account", "status": "Active"}


async def test_core_status_refuses_a_capability_that_is_a_path():
  def no_calls(request):
    raise AssertionError(f"unexpected call to {request.url.path}")

  async with Client(mcp_server.build(["core"], client=client_for(no_calls))) as client:
    result = await client.call_tool("status", {"capability": "../environments/demo"})
  assert result.is_error
