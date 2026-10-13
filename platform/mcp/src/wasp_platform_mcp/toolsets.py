"""Toolsets: groups of tools an agent enables by name, so it loads only the slice it uses (ADR 0027).

Every tool is a thin call to one Platform API route through the CLI client: no logic of its own.
Authorization, validation and the journal stay in the API.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from wasp_platform.client import PlatformClient

ClientFactory = Callable[[], PlatformClient]


@dataclass(frozen=True)
class ToolSpec:
  name: str
  fn: Callable[..., Any]
  # Read-only by default; a write tool is registered only with --allow-writes.
  write: bool = False
  destructive: bool = False
  idempotent: bool = True


def core(client: ClientFactory) -> list[ToolSpec]:
  def whoami() -> dict[str, Any]:
    """Who the Platform API sees the caller as: sub, email, groups and teams."""
    return client().me()

  return [ToolSpec("whoami", whoami)]


def environments(client: ClientFactory) -> list[ToolSpec]:
  def environments_list(all: bool = False) -> dict[str, Any]:
    """Environments the caller owns or that are shared with their teams; all=true lists every one (platform-admins only)."""
    return {"items": client().list_environments(all)}

  def environments_get(name: str) -> dict[str, Any]:
    """One environment: profile, status (pending, ready, deleting or a failure reason), expiresAt, owner and the URL of its workloads."""
    environment = client().get_environment(name)
    # The personal kubeconfig of the caller (ADR 0028) never reaches the agent.
    environment.pop("kubeconfigData", None)
    return environment

  def environments_create(name: str, profile: Literal["ephemeral", "shared"], expires: str) -> dict[str, Any]:
    """Request a new environment, which expires after the given lifetime (30m, 12h, 3d or 1w).

    The platform answers right away with status pending; call environments_get until status is ready.
    """
    # The API cannot tell an agent from the user yet (ADR 0027, phase 1): this server makes the
    # lifetime mandatory for agents until #219 moves the rule to the API.
    if not expires.strip():
      raise ToolError("an agent must set expires on a new environment, such as 2h or 1d")
    return client().create_environment(name, profile, expires)

  return [
    ToolSpec("environments_list", environments_list),
    ToolSpec("environments_get", environments_get),
    ToolSpec("environments_create", environments_create, write=True, idempotent=False),
  ]


TOOLSETS: dict[str, Callable[[ClientFactory], list[ToolSpec]]] = {
  "core": core,
  "environments": environments,
}
