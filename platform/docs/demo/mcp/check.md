# Check the connection

```bash
claude mcp list | grep platform
```

``` { .text .output title="output" }
platform: platform-mcp --toolsets core,environments,catalog,builds,workloads --allow-writes - ✔ Connected
```

Start a **new** Claude Code session and type `/mcp`: `platform` lists 22 tools.
