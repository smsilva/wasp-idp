"""Builds the MCP server from the enabled toolsets and runs it over stdio (ADR 0027, phase 1)."""
import argparse
import functools
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from wasp_platform.client import ApiError, PlatformClient

from .toolsets import TOOLSETS, ClientFactory, ToolSpec

DEFAULT_TOOLSETS = ["core"]

INSTRUCTIONS = (
  "Tools of the wasp-idp internal developer platform. Each tool calls the Platform API "
  "as the user logged in with the platform CLI; the API decides what the user may do."
)


def build(toolsets: list[str], allow_writes: bool = False, client: ClientFactory = PlatformClient) -> MCPServer:
  unknown = [name for name in toolsets if name not in TOOLSETS]
  if unknown:
    raise ValueError(f"unknown toolset(s): {', '.join(unknown)} (available: {', '.join(TOOLSETS)})")
  # WARNING: the httpx line of every API call would flood the agent's server log.
  server = MCPServer("platform", instructions=INSTRUCTIONS, log_level="WARNING")
  for name in dict.fromkeys(toolsets):
    for spec in TOOLSETS[name](client):
      if spec.write and not allow_writes:
        continue
      server.add_tool(_api_errors_as_tool_errors(spec.fn), name=spec.name, annotations=_annotations(spec))
  return server


def _annotations(spec: ToolSpec) -> ToolAnnotations:
  return ToolAnnotations(
    readOnlyHint=not spec.write,
    destructiveHint=spec.destructive if spec.write else None,
    idempotentHint=spec.idempotent if spec.write else None,
    openWorldHint=False,
  )


def _api_errors_as_tool_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
  """The API message reaches the model as a tool error, without a traceback."""
  @functools.wraps(fn)
  def wrapper(*args, **kwargs):
    try:
      return fn(*args, **kwargs)
    except ApiError as error:
      raise ToolError(str(error)) from error
  return wrapper


def main(argv: list[str] | None = None) -> None:
  parser = argparse.ArgumentParser(
    prog="platform-mcp",
    description="MCP server of the wasp-idp Platform API, over stdio. Uses the login of the platform CLI.",
  )
  parser.add_argument(
    "--toolsets",
    default=",".join(DEFAULT_TOOLSETS),
    help=f"comma-separated toolsets to enable (available: {', '.join(TOOLSETS)}; default: %(default)s)",
  )
  parser.add_argument(
    "--allow-writes",
    action="store_true",
    help="also register the tools that change the platform (read-only by default)",
  )
  args = parser.parse_args(argv)
  toolsets = [name.strip() for name in args.toolsets.split(",") if name.strip()]
  try:
    server = build(toolsets, allow_writes=args.allow_writes)
  except ValueError as error:
    parser.error(str(error))
  server.run("stdio")
