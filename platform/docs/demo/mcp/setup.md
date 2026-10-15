# Connect the agent

```bash
claude mcp add platform \
  --scope user -- \
    platform-mcp \
      --toolsets core,environments,catalog,builds,workloads \
      --allow-writes
```
