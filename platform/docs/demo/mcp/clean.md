# Start clean

No `platform` server registered in Claude Code, so [Connect the agent](setup.md) starts from scratch:

```bash
claude mcp remove \
  --scope local \
  platform

claude mcp remove \
  --scope user \
  platform
```
