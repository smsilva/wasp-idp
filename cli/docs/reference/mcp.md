# MCP server

`platform-mcp` exposes the Platform API to AI agents as an MCP server over **stdio** (ADR 0027): the agent's MCP client starts it as a subprocess. It is a thin adapter: each tool is one call to a `/v1/*` route, with the login of the CLI (`platform login`, refreshed the same way). Install it with `make mcp`; `make mcp-uninstall` removes it.

```bash
platform-mcp \
  --toolsets core \
  --allow-writes
```

| Flag | Default | Meaning |
|---|---|---|
| `--toolsets` | `core` | Comma-separated toolsets to enable; an unknown name stops the server with the list of the available ones. |
| `--allow-writes` | off | Also register the tools that change the platform. Without it, only read-only tools exist. |

The server reads the same configuration as the CLI: `api_url` from `~/.config/platform/config.yaml` (or `PLATFORM_API_URL`) and the credentials of `platform login`, both under `XDG_CONFIG_HOME` when it is set.

## Toolsets

| Toolset | Tool | Route | Annotations |
|---|---|---|---|
| `core` | `whoami` | `GET /v1/me` | read-only |

Every tool carries the MCP annotations: `readOnlyHint`, and for a write tool `destructiveHint` and `idempotentHint`. Tool names follow `<toolset>_<verb>` (`environments_list`); `core` tools have no prefix.

## Errors

An API error reaches the agent as a tool error with the status and the API message (`<status>: <message>`), never a traceback. Without a login, every tool answers `not logged in: run 'platform login'`; with an expired one, `session expired: run 'platform login'`.
