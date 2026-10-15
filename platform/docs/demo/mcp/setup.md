# Connect the agent

Add `platform` MCP:

```bash
claude mcp add platform \
  --scope user -- \
    platform-mcp \
      --toolsets core,environments,catalog,builds,workloads \
      --allow-writes
```
