import httpx
import pytest
from mcp import Client
from wasp_platform.client import PlatformClient

from wasp_platform_mcp import server as mcp_server

DOMAIN = {"kind": "Domain", "name": "platform", "owner": "team-platform", "parent": None, "dependents": ["system/platform"]}

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
  return "asyncio"


def client_for(handler):
  return lambda: PlatformClient(base_url="http://api", transport=httpx.MockTransport(handler), token=lambda: "t")


def no_calls(request):
  raise AssertionError(f"unexpected call to {request.method} {request.url.path}")


async def call(tool: str, arguments: dict, handler=no_calls):
  async with Client(mcp_server.build(["catalog"], client=client_for(handler))) as client:
    return await client.call_tool(tool, arguments)


async def test_every_tool_is_read_only_even_with_allow_writes():
  async with Client(mcp_server.build(["catalog"], allow_writes=True, client=client_for(no_calls))) as client:
    tools = (await client.list_tools()).tools
  assert sorted(tool.name for tool in tools) == [
    "catalog_components_creation_get",
    "catalog_components_get",
    "catalog_components_list",
    "catalog_get",
    "catalog_list",
    "catalog_templates_get",
    "catalog_templates_list",
  ]
  assert all(tool.annotations.read_only_hint for tool in tools)


async def test_list_filters_by_kind_and_owner():
  def handler(request):
    assert request.url.path == "/v1/catalog/entities"
    assert dict(request.url.params) == {"kind": "system", "owner": "team-a"}
    return httpx.Response(200, json={"items": []})

  result = await call("catalog_list", {"kind": "system", "owner": "team-a"}, handler)
  assert result.structured_content == {"items": []}


@pytest.mark.parametrize("kind", ["domain", "system", "resource"])
async def test_get_uses_the_plural_of_the_kind(kind):
  def handler(request):
    assert request.url.path == f"/v1/catalog/{kind}s/platform"
    return httpx.Response(200, json=DOMAIN)

  result = await call("catalog_get", {"kind": kind, "name": "platform"}, handler)
  assert result.structured_content == DOMAIN


async def test_get_rejects_an_unknown_kind_before_the_api():
  result = await call("catalog_get", {"kind": "component", "name": "x"})
  assert result.is_error


async def test_components_list_filters_by_system_and_owner():
  def handler(request):
    assert request.url.path == "/v1/catalog/components"
    assert dict(request.url.params) == {"system": "platform"}
    return httpx.Response(200, json={"items": [{"name": "details"}]})

  result = await call("catalog_components_list", {"system": "platform"}, handler)
  assert result.structured_content == {"items": [{"name": "details"}]}


@pytest.mark.parametrize(("tool", "path"), [
  ("catalog_components_get", "/v1/catalog/components/details"),
  ("catalog_components_creation_get", "/v1/catalog/components/details/creation"),
  ("catalog_templates_get", "/v1/catalog/templates/details"),
])
async def test_single_reads(tool, path):
  def handler(request):
    assert request.url.path == path
    return httpx.Response(200, json={"name": "details"})

  result = await call(tool, {"name": "details"}, handler)
  assert result.structured_content == {"name": "details"}


async def test_templates_list():
  def handler(request):
    assert request.url.path == "/v1/catalog/templates"
    return httpx.Response(200, json={"items": [{"name": "python-service"}]})

  result = await call("catalog_templates_list", {}, handler)
  assert result.structured_content == {"items": [{"name": "python-service"}]}


async def test_creation_of_someone_else_is_a_tool_error():
  def handler(request):
    return httpx.Response(403, json={"error": {"code": "forbidden", "message": "the creation of 'details' is visible to who requested it and platform-admins"}})

  result = await call("catalog_components_creation_get", {"name": "details"}, handler)
  assert result.is_error
  assert "visible to who requested it" in result.content[0].text
