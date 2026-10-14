# Create an environment

The one tool that changes the platform:

```text
Create an ephemeral environment called agent-demo for 2 hours and tell me when it is ready.
```

| Tool | |
|---|---|
| `environments_create` | `agent-demo`, `ephemeral`, `expires: 2h` |
| `environments_get` | until it is `ready` |

The server refuses an environment without an expiration. Check it from the CLI:

```bash
platform environment list
```
