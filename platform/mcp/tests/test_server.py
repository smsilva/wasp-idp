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


async def test_core_lists_whoami_as_read_only():
  async with Client(mcp_server.build(["core"], client=client_for(me_handler))) as client:
    tools = (await client.list_tools()).tools
  assert [tool.name for tool in tools] == ["whoami"]
  assert tools[0].annotations.read_only_hint is True


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
