"""Toolsets: groups of tools an agent enables by name, so it loads only the slice it uses (ADR 0027).

Every tool is a thin call to one Platform API route through the CLI client: no logic of its own.
Authorization, validation and the journal stay in the API.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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


TOOLSETS: dict[str, Callable[[ClientFactory], list[ToolSpec]]] = {
  "core": core,
}
