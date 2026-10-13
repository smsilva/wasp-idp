# Connect an AI agent

`platform-mcp` is the platform's **MCP server**: an AI agent (Claude Code or any other MCP client) calls the Platform API through it, with the same answers the CLI gets. Every tool calls one `/v1/*` route; the API decides what is allowed and writes the audit trail (ADR 0027).

```bash
make mcp                       # puts platform-mcp on the PATH, editable from this checkout

platform login                 # the server uses this login

claude mcp add platform -- platform-mcp --toolsets core
```

Then ask the agent: *"Who am I on the platform?"* It calls the `whoami` tool, which answers with the same `sub`, email and groups as `platform whoami --output json`.

Another MCP client takes the same command in its configuration:

```json
{
  "mcpServers": {
    "platform": {
      "command": "platform-mcp",
      "args": ["--toolsets", "core"]
    }
  }
}
```

!!! warning
    In this first phase the agent acts **with your token**: it can do what you can do, and the audit trail records you, not the agent. Tools that change the platform are off unless the server starts with `--allow-writes`. Agents with their own identity, acting on your behalf, come with #219.
