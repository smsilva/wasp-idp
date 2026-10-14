# Connect the agent

Register the server, with every toolset and the tools that change the platform:

```bash
claude mcp add --scope user platform -- platform-mcp \
  --toolsets core,environments,catalog,builds \
  --allow-writes
```

```bash
claude mcp list | grep platform
```

``` { .text .output title="output" }
platform: platform-mcp --toolsets core,environments,catalog,builds --allow-writes - ✔ Connected
```

Start a **new** Claude Code session and type `/mcp`: `platform` lists 17 tools.
