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
| `core` | `status` | `GET /v1/capabilities`, or `GET /v1/capabilities/{capability}` | read-only |
| `environments` | `environments_list` | `GET /v1/environments` (`all=true` lists every environment, `platform-admins` only) | read-only |
| `environments` | `environments_get` | `GET /v1/environments/{name}`, without `kubeconfigData` | read-only |
| `environments` | `environments_create` | `POST /v1/environments` | write, not destructive, not idempotent |
| `environments` | `environments_delete` | `DELETE /v1/environments/{name}`, ephemeral only | write, destructive, idempotent |
| `catalog` | `catalog_list` | `GET /v1/catalog/entities` (`kind`: `domain`, `system` or `resource`; `owner`) | read-only |
| `catalog` | `catalog_get` | `GET /v1/catalog/{kind}s/{name}`, with its `dependents` | read-only |
| `catalog` | `catalog_components_list` | `GET /v1/catalog/components` (`system`, `owner`) | read-only |
| `catalog` | `catalog_components_get` | `GET /v1/catalog/components/{name}`, with `runningIn` | read-only |
| `catalog` | `catalog_components_creation_get` | `GET /v1/catalog/components/{name}/creation` | read-only |
| `catalog` | `catalog_templates_list` | `GET /v1/catalog/templates` | read-only |
| `catalog` | `catalog_templates_get` | `GET /v1/catalog/templates/{name}` | read-only |

`status` answers like `platform status` (ADR 0039): each capability with its status, and for `platform-admins` the drivers that implement it and the fix of a failing one.

`environments_get` drops the personal kubeconfig the API returns to the people who can use the environment (ADR 0028): a kubeconfig never reaches the agent. `environments_create` takes `name`, `profile` (`ephemeral` or `shared`) and a **mandatory** `expires` (`30m`, `12h`, `3d`, `1w`); without it the server refuses before calling the API. The API answers right away with status `pending`, and the agent calls `environments_get` until it is `ready`. `environments_delete` deletes only `ephemeral` environments: it reads the environment first and refuses any other profile before calling the API, since destructive actions on the rest wait for human approval (#220). The API answers with status `deleting`. In this first phase the API cannot tell an agent from you, so the server carries both rules until agents get their own identity (#219). Sharing with a team is not a tool yet.

The `catalog` toolset only reads, in the vocabulary of ADR 0023: creating a component or a build from an agent comes after #219. `catalog_components_get` lists where the component runs only in the environments you can use, and `catalog_components_creation_get` answers only to who requested the creation and `platform-admins`. APIs are not a tool yet: the API has no route for them until #205 imports them from `catalog-info.yaml`.

Every tool carries the MCP annotations: `readOnlyHint`, and for a write tool `destructiveHint` and `idempotentHint`. Tool names follow `<toolset>_<verb>` (`environments_list`); `core` tools have no prefix.

## Errors

An API error reaches the agent as a tool error with the status and the API message (`<status>: <message>`), never a traceback. Without a login, every tool answers `not logged in: run 'platform login'`; with an expired one, `session expired: run 'platform login'`.
