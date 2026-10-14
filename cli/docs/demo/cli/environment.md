# Create an environment

An environment is a Kubernetes cluster of its own (a vcluster), ready in about a minute:

```bash
platform environment create demo \
  --profile shared \
  --expires 2h \
  --wait
```

``` { .text .output title="output" }
provisioning demo (profile: shared) …
  NoProviderForCapability
  Provisioning
✓ demo ready
```

- **Profile:** `shared` keeps its data, so each app gets a Postgres of its own. `ephemeral` ([A second environment](second.md)) puts them in a shared instance.
- **Expiry:** `--expires` deletes it on its own.
- **Access:** private to you unless shared with a team (`--share-with`).
