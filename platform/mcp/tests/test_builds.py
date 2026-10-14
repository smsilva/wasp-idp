import json

import httpx
import pytest
from mcp import Client
from wasp_platform.client import PlatformClient

from wasp_platform_mcp import server as mcp_server

BUILD = {
  "kind": "Build",
  "name": "hello-api-1a2b3c",
  "component": "hello-api",
  "branch": "feat/greetings",
  "requestedVersion": None,
  "registry": "ghcr-wasp-foundry",
  "status": "pending",
}
VERSION = {"kind": "Version", "name": "hello-api.0.1.0-greetings.b5f9569", "component": "hello-api", "version": "0.1.0-greetings.b5f9569"}

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
  return "asyncio"


def client_for(handler):
  return lambda: PlatformClient(base_url="http://api", transport=httpx.MockTransport(handler), token=lambda: "t")


def no_calls(request):
  raise AssertionError(f"unexpected call to {request.method} {request.url.path}")


async def tools(**kwargs) -> dict:
  async with Client(mcp_server.build(["builds"], client=client_for(no_calls), **kwargs)) as client:
    return {tool.name: tool for tool in (await client.list_tools()).tools}


async def test_read_only_by_default():
  assert sorted(await tools()) == ["builds_get", "builds_list", "builds_versions_list"]


async def test_create_needs_allow_writes_and_is_not_idempotent():
  create = (await tools(allow_writes=True))["builds_create"]
  assert create.annotations.read_only_hint is False
  assert create.annotations.destructive_hint is False
  assert create.annotations.idempotent_hint is False
  assert sorted(create.input_schema["required"]) == ["branch", "component"]


async def test_create_sends_only_the_given_fields():
  def handler(request):
    assert (request.method, request.url.path) == ("POST", "/v1/builds")
    assert json.loads(request.content) == {"component": "hello-api", "branch": "feat/greetings"}
    return httpx.Response(202, json=BUILD)

  async with Client(mcp_server.build(["builds"], allow_writes=True, client=client_for(handler))) as client:
    result = await client.call_tool("builds_create", {"component": "hello-api", "branch": "feat/greetings"})
  assert not result.is_error
  assert result.structured_content == BUILD


async def test_create_with_version_and_registry():
  def handler(request):
    assert json.loads(request.content) == {"component": "hello-api", "branch": "main", "version": "1.0.0", "registry": "ghcr-wasp-foundry"}
    return httpx.Response(202, json={**BUILD, "requestedVersion": "1.0.0"})

  async with Client(mcp_server.build(["builds"], allow_writes=True, client=client_for(handler))) as client:
    result = await client.call_tool("builds_create", {"component": "hello-api", "branch": "main", "version": "1.0.0", "registry": "ghcr-wasp-foundry"})
  assert result.structured_content["requestedVersion"] == "1.0.0"


async def test_get_reads_one_build():
  def handler(request):
    assert request.url.path == "/v1/builds/hello-api-1a2b3c"
    return httpx.Response(200, json={**BUILD, "status": "ready"})

  async with Client(mcp_server.build(["builds"], client=client_for(handler))) as client:
    result = await client.call_tool("builds_get", {"name": "hello-api-1a2b3c"})
  assert result.structured_content["status"] == "ready"


async def test_get_refuses_a_name_that_is_a_path():
  async with Client(mcp_server.build(["builds"], client=client_for(no_calls))) as client:
    result = await client.call_tool("builds_get", {"name": "../environments/demo"})
  assert result.is_error
  assert "is not a platform name" in result.content[0].text


async def test_list_filters_by_component():
  def handler(request):
    assert request.url.path == "/v1/builds"
    assert request.url.params.get("component") == "hello-api"
    return httpx.Response(200, json={"items": [BUILD]})

  async with Client(mcp_server.build(["builds"], client=client_for(handler))) as client:
    result = await client.call_tool("builds_list", {"component": "hello-api"})
  assert result.structured_content == {"items": [BUILD]}


async def test_builds_versions_list_filters_by_component():
  def handler(request):
    assert request.url.path == "/v1/versions"
    assert request.url.params.get("component") == "hello-api"
    return httpx.Response(200, json={"items": [VERSION]})

  async with Client(mcp_server.build(["builds"], client=client_for(handler))) as client:
    result = await client.call_tool("builds_versions_list", {"component": "hello-api"})
  assert result.structured_content == {"items": [VERSION]}
