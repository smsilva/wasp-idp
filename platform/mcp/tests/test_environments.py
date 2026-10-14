import json

import httpx
import pytest
from mcp import Client
from wasp_platform.client import PlatformClient

from wasp_platform_mcp import server as mcp_server

DEMO = {
  "name": "demo",
  "profile": "ephemeral",
  "expiresAt": "2026-10-13T12:00:00Z",
  "status": "ready",
  "message": None,
  "port": 7100,
  "ingress": "http://*.demo.localhost:7080",
  "createdAt": "2026-10-13T10:00:00Z",
  "owner": "dev@example.com",
  "sharedWith": [],
}

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
  return "asyncio"


def client_for(handler):
  return lambda: PlatformClient(base_url="http://api", transport=httpx.MockTransport(handler), token=lambda: "t")


def no_calls(request):
  raise AssertionError(f"unexpected call to {request.method} {request.url.path}")


async def tool_names(**kwargs) -> dict:
  async with Client(mcp_server.build(["environments"], client=client_for(no_calls), **kwargs)) as client:
    return {tool.name: tool for tool in (await client.list_tools()).tools}


async def test_read_only_by_default():
  assert sorted(await tool_names()) == ["environments_get", "environments_list"]


async def test_create_needs_allow_writes_and_is_not_destructive():
  tools = await tool_names(allow_writes=True)
  create = tools["environments_create"]
  assert create.annotations.read_only_hint is False
  assert create.annotations.destructive_hint is False
  assert create.annotations.idempotent_hint is False
  assert "expires" in create.input_schema["required"]
  assert "sharedWith" not in create.input_schema["properties"]


async def test_list_passes_all():
  def handler(request):
    assert request.url.path == "/v1/environments"
    assert request.url.params.get("all") == "true"
    return httpx.Response(200, json={"items": [DEMO]})

  async with Client(mcp_server.build(["environments"], client=client_for(handler))) as client:
    result = await client.call_tool("environments_list", {"all": True})
  assert result.structured_content == {"items": [DEMO]}


async def test_get_strips_the_kubeconfig():
  def handler(request):
    assert request.url.path == "/v1/environments/demo"
    return httpx.Response(200, json={**DEMO, "kubeconfigData": "apiVersion: v1\n"})

  async with Client(mcp_server.build(["environments"], client=client_for(handler))) as client:
    result = await client.call_tool("environments_get", {"name": "demo"})
  assert not result.is_error
  assert result.structured_content == DEMO
  assert "kubeconfig" not in result.content[0].text


async def test_create_sends_name_profile_and_expires():
  def handler(request):
    assert (request.method, request.url.path) == ("POST", "/v1/environments")
    assert json.loads(request.content) == {"name": "demo", "profile": "ephemeral", "expires": "2h"}
    return httpx.Response(202, json={**DEMO, "status": "pending"})

  async with Client(mcp_server.build(["environments"], allow_writes=True, client=client_for(handler))) as client:
    result = await client.call_tool("environments_create", {"name": "demo", "profile": "ephemeral", "expires": "2h"})
  assert not result.is_error
  assert result.structured_content["status"] == "pending"


@pytest.mark.parametrize("arguments", [{"name": "demo", "profile": "ephemeral"}, {"name": "demo", "profile": "ephemeral", "expires": " "}])
async def test_create_refuses_without_expires_before_the_api(arguments):
  async with Client(mcp_server.build(["environments"], allow_writes=True, client=client_for(no_calls))) as client:
    result = await client.call_tool("environments_create", arguments)
  assert result.is_error
  assert "expires" in result.content[0].text


async def test_create_rejects_an_unknown_profile():
  async with Client(mcp_server.build(["environments"], allow_writes=True, client=client_for(no_calls))) as client:
    result = await client.call_tool("environments_create", {"name": "demo", "profile": "prod", "expires": "2h"})
  assert result.is_error


@pytest.mark.parametrize("name", ["demo/admin-kubeconfig", "../catalog/domains/x", "demo\n"])
async def test_get_refuses_a_name_that_is_a_path(name):
  async with Client(mcp_server.build(["environments"], client=client_for(no_calls))) as client:
    result = await client.call_tool("environments_get", {"name": name})
  assert result.is_error
  assert "is not a platform name" in result.content[0].text


async def test_delete_needs_allow_writes_and_is_destructive():
  assert "environments_delete" not in await tool_names()
  delete = (await tool_names(allow_writes=True))["environments_delete"]
  assert delete.annotations.read_only_hint is False
  assert delete.annotations.destructive_hint is True
  assert delete.annotations.idempotent_hint is True


async def test_delete_removes_an_ephemeral_environment():
  calls = []

  def handler(request):
    calls.append((request.method, request.url.path))
    if request.method == "GET":
      return httpx.Response(200, json=DEMO)
    return httpx.Response(202, json={"name": "demo", "status": "deleting"})

  async with Client(mcp_server.build(["environments"], allow_writes=True, client=client_for(handler))) as client:
    result = await client.call_tool("environments_delete", {"name": "demo"})
  assert not result.is_error
  assert result.structured_content == {"name": "demo", "status": "deleting"}
  assert calls == [("GET", "/v1/environments/demo"), ("DELETE", "/v1/environments/demo")]


async def test_delete_refuses_a_shared_environment_before_the_api():
  def handler(request):
    assert request.method == "GET"
    return httpx.Response(200, json={**DEMO, "profile": "shared"})

  async with Client(mcp_server.build(["environments"], allow_writes=True, client=client_for(handler))) as client:
    result = await client.call_tool("environments_delete", {"name": "demo"})
  assert result.is_error
  assert "ephemeral" in result.content[0].text


async def test_delete_refuses_a_name_that_is_a_path():
  async with Client(mcp_server.build(["environments"], allow_writes=True, client=client_for(no_calls))) as client:
    result = await client.call_tool("environments_delete", {"name": "../catalog/domains/x"})
  assert result.is_error
  assert "is not a platform name" in result.content[0].text
