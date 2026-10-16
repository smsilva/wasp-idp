# A second environment

An `ephemeral` environment:

```bash
platform environment create checkin-test \
  --profile ephemeral \
  --expires 2h \
  --wait
```

The same version, deployed there:

```bash
platform workload deploy \
  --component seat-selection \
  --environment checkin-test \
  --branch feat/seat-pick \
  --wait
```
