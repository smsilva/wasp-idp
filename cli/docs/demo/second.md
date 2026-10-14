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

Call it:

```bash
curl --include http://hello-api.greetings-test.localhost:7080/
```

Where the app runs now:

```bash
platform catalog component get hello-api
```
