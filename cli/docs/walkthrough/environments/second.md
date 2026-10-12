# A second environment

```bash
platform environment create demo \
  --profile shared \
  --expires 1h \
  --wait

platform environment get demo

platform environment list --output json
```

`demo` is `shared`: an environment whose data stays, so its databases are made the way the platform default says ([A database for a workload](../workloads/resources.md)). An `ephemeral` one gets them in the shared instance ([A database in the shared instance](../workloads/compose.md)).

!!! note
    Each environment gets the **next free port** in the `7100`–`7119` range (`demo` gets `7101`).
