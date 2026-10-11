# A second environment

```bash
platform environment create demo \
  --profile ephemeral \
  --expires 1h \
  --wait

platform environment get demo

platform environment list --output json
```

!!! note
    Each environment gets the **next free port** in the `7100`–`7119` range (`demo` gets `7101`).
