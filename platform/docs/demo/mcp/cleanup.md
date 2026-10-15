# Wrap up

Ask the agent to delete what it made:

```text
Delete the agent-demo environment.
```

| Tool | |
|---|---|
| `environments_delete` | only `ephemeral` environments: a `shared` one is deleted with `platform environment delete` |

Back to the read-only server:

```bash
claude mcp remove \
  --scope user \
  platform
```

```bash
claude mcp add platform \
  --scope user -- \
    platform-mcp \
      --toolsets core,environments,catalog,builds,workloads
```
