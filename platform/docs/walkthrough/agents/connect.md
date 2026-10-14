# Connect an AI agent

`platform-mcp` is the platform's **MCP server**: an AI agent (Claude Code or any other MCP client) calls the Platform API through it, with the same answers the CLI gets. Every tool calls one `/v1/*` route; the API decides what is allowed and writes the audit trail (ADR 0027). This step comes last because the agent works on what the walkthrough built: the environment `demo`, the catalog of `team-alpha` and the component `hello-api`.

| Toolset | What the agent can do |
|---|---|
| `core` | `whoami`: who the platform sees; `status`: which capabilities work |
| `environments` | list and read environments; create one, with an expiration, and delete an ephemeral one, only with `--allow-writes` |
| `catalog` | read domains, systems, resources, components and templates |
| `builds` | read builds and versions; build a branch only with `--allow-writes` |
| `workloads` | read what runs in an environment: instances, revisions and golden signals; deploy a version only with `--allow-writes` |

## Set it up

The server runs on this machine (stdio): Claude Code starts it when a session starts, and it uses your `platform login`.

=== "Ask your agent"

    Open Claude Code in this repo's checkout and paste:

    ```text
    Set up the wasp-idp MCP server for Claude Code on this machine:
    1. Run `make mcp` in this repository and check that `platform-mcp --help` works.
    2. Run `platform whoami`. If it says I am not logged in, stop and ask me to run `platform login`.
    3. Remove any server named `platform` from both scopes: `claude mcp remove --scope local platform` and `claude mcp remove --scope user platform` (a "not found" from either is fine).
    4. Run `claude mcp add --scope user platform -- platform-mcp --toolsets core,environments,catalog,builds,workloads`.
    5. Run `claude mcp list` and show me the `platform` line.
    6. Tell me to start a new Claude Code session, so it loads the server.
    Do not add --allow-writes.
    ```

=== "Manual"

    ```bash
    make mcp                       # puts platform-mcp on the PATH, editable from this checkout

    platform whoami                # the server uses this login; run platform login if it fails

    claude mcp remove --scope local platform   # an older registration here wins over the user one
    claude mcp remove --scope user platform    # a "not found" from either is fine

    claude mcp add --scope user platform -- platform-mcp \
      --toolsets core,environments,catalog,builds,workloads
    ```

    `--scope user` makes the server available in every directory; without it, Claude Code keeps it only for the current one. A `platform` left in the local scope, by an `add` without `--scope user`, wins over the user one in this directory, with the toolsets it had then: that is why both `remove` lines come first.

Then start a **new** Claude Code session: a running session does not load servers added after it started.

## Check it

```bash
claude mcp list | grep platform
```

``` { .text .output title="output" }
platform: platform-mcp --toolsets core,environments,catalog,builds,workloads - ✔ Connected
```

Inside the session, `/mcp` lists `platform` with its tools. Ask the first question:

```text
Who am I on the platform?
```

The agent calls `whoami`, which answers with the same `sub`, email and groups as `platform whoami --output json`.

```text
Is the platform working?
```

The agent calls `status`, the same capabilities as `platform status`.

## Ask about environments and the catalog

Everything here only reads:

```text
Which environments do I have, what is their status, and when do they expire?
```

The agent calls `environments_list` and `environments_get`. It never sees a kubeconfig: you get yours with `platform environment get demo`.

```text
Which systems does team-alpha own, which components belong to greeter, and where does hello-api run?
```

The agent calls `catalog_list` with `kind: system` and `owner: team-alpha`, `catalog_components_list` with `system: greeter`, then `catalog_components_get` for `hello-api`, whose `runningIn` lists only the environments you can use.

## Let the agent create an environment

Tools that change the platform exist only when the server starts with `--allow-writes`. Replace the server:

```bash
claude mcp remove --scope user platform

claude mcp add --scope user platform -- platform-mcp \
  --toolsets core,environments,catalog,builds,workloads \
  --allow-writes
```

In a new session:

```text
Create an ephemeral environment called agent-demo for 2 hours and tell me when it is ready.
```

The agent calls `environments_create` with `expires: 2h`, then `environments_get` until the status is `ready`, and answers with the URL of its workloads. The server refuses a new environment without an expiration.

```text
Delete the agent-demo environment.
```

The agent calls `environments_delete`. It deletes only `ephemeral` environments: a `shared` one is deleted by you, with `platform environment delete`.

## Another MCP client

Any MCP client takes the same command in its configuration:

```json
{
  "mcpServers": {
    "platform": {
      "command": "platform-mcp",
      "args": ["--toolsets", "core,environments,catalog,builds,workloads"]
    }
  }
}
```

!!! warning
    In this first phase the agent acts **with your token**: it can do what you can do, and the audit trail records you, not the agent. Agents with their own identity, acting on your behalf, come with #219.

Every tool, its route and its flags are in the [reference](../../reference/mcp.md).
