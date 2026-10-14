# A second environment

An `ephemeral` environment:

```bash
platform environment create greetings-test \
  --profile ephemeral \
  --expires 2h \
  --wait
```

The same version, deployed there:

```bash
platform workload deploy \
  --component hello-api \
  --environment greetings-test \
  --branch feat/greetings \
  --wait
```
