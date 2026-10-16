# Delete the environments

Deleting an environment takes everything in it: workloads, revisions, and the databases made for it.

```bash
platform environment delete demo

platform environment delete checkin-test

platform environment delete agent-demo
```

``` { .text .output title="output" }
✓ demo deleting
✓ checkin-test deleting
✓ agent-demo deleting
```

The delete returns at once; the provider removes each vcluster in the background. Once the namespaces are gone:

```bash
kubectl --context k3d-platform-local get namespaces \
  | grep env- \
  || echo "no environments"
```

``` { .text .output title="output" }
no environments
```

`agent-demo` is the one the agent created in [Connect an AI agent](../agents/connect.md); deleting is not an MCP tool yet.
