# A second environment

```bash
platform environment create checkin-test \
  --profile ephemeral \
  --expires 1h \
  --wait

platform environment get checkin-test

platform environment list --output json
```

`checkin-test` is `ephemeral`: a short-lived environment, so its databases go to the shared instance ([A database in the shared instance](../workloads/resources/compose.md)) instead of a Postgres of their own.

!!! note
    Each environment gets the **next free port** in the `7100`–`7119` range (`checkin-test` gets `7101`).
