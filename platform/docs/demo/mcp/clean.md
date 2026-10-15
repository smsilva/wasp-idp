# Start clean

No `platform` server registered in Claude Code, so [Connect the agent](setup.md) starts from scratch:

```bash
for scope in "local" "user"; do
  claude mcp remove platform \
    --scope "${scope}"
done
```
