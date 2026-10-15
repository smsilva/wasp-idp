# Where the app runs

```bash
platform catalog component get hello-api
```

``` { .text .output title="output" }
component/hello-api
  system       greeter
  owner        team-alpha
  type         service
  lifecycle    experimental
  repo         wasp-foundry/hello-api
  template     python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
  description  —
  creation     ready, 2h ago
  builds       hello-api-6cf484 (ready, 0.1.0-greetings.b5f9569, 1h)
  versions     0.1.0-greetings.b5f9569 (b5f9569, feat/greetings, 1h)
  running in   demo (0.1.0-greetings.b5f9569, Available), greetings-test (0.1.0-greetings.b5f9569, Available)

next:

  platform build get hello-api-6cf484

  platform build list \
    --component hello-api

  platform workload list \
    --component hello-api

  platform catalog component creation get hello-api

  platform catalog component clone hello-api
```
