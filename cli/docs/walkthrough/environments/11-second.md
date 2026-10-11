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
    Cada ambiente ganha a **próxima porta livre** da faixa `7100`–`7119` (`demo` fica na `7101`).
