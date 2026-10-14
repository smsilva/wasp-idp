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
  running in   demo (0.1.0-greetings.b5f9569, Available), greetings-test (0.1.0-greetings.b5f9569, Available)
```
