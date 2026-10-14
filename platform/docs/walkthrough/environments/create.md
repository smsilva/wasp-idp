# Create an environment

`hello-api` has a version: now it needs somewhere to run. `demo` is `shared`, an environment whose data stays, so its databases are made the way the platform default says ([A database for a workload](../workloads/resources/provision.md)).

```bash
time platform environment create demo \
  --profile shared \
  --expires 1h \
  --wait
```

``` { .text .output title="output" }
provisioning demo (profile: shared) …
  NoProviderForCapability
  Provisioning
✓ demo ready

real    0m51s
```

!!! note
    The request starts at `NoProviderForCapability` and the `local_vcluster` provider, which runs inside `platform-local`, picks it up right after. **There is no second terminal.**
