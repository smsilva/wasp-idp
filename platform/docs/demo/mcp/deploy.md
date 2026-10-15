# Deploy it

```text
Deploy the version you just built to agent-demo and tell me when it runs.
```

| Tool | |
|---|---|
| `workloads_deploy` | `agent-demo`, `hello-api`, the version from the build |
| `workloads_history` | until the revision closes, `Succeeded` |
| `workloads_get` | the URL of `hello-api` in `agent-demo` |

The API answers right away with an open revision, as `platform workload deploy` without `--wait`. Check it from the CLI:

```bash
platform workload get hello-api --environment agent-demo
```
