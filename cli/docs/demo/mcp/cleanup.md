# After the demo

Deleting is not a tool yet:

```bash
platform environment delete agent-demo
```

Back to the read-only server:

```bash
claude mcp remove --scope user platform
```

```bash
claude mcp add --scope user platform -- platform-mcp \
  --toolsets core,environments,catalog
```
