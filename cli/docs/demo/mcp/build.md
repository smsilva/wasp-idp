# Build a branch

```text
Build the feat/greetings branch of hello-api and tell me the version it registers.
```

| Tool | |
|---|---|
| `builds_create` | `hello-api`, `feat/greetings` |
| `builds_get` | until it is `ready`, about a minute |
| `builds_versions_list` | the version the build registered |

The platform dispatches the repo's CI workflow, as in `platform build create`. Check it from the CLI:

```bash
platform build list --component hello-api
```
