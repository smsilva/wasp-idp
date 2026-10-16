# Where the app runs

```bash
platform catalog component get seat-selection
```

``` { .text .output title="output" }
component/seat-selection
  system       seat-map
  owner        team-airport
  type         service
  lifecycle    experimental
  repo         wasp-foundry/seat-selection
  template     python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
  description  —
  creation     ready, 2h ago
  builds       seat-selection-6cf484 (ready, 0.1.0-seat-pick.b5f9569, 1h)
  versions     0.1.0-seat-pick.b5f9569 (b5f9569, feat/seat-pick, 1h)
  running in   demo (0.1.0-seat-pick.b5f9569, Available), checkin-test (0.1.0-seat-pick.b5f9569, Available)

next:

  platform build get seat-selection-6cf484

  platform build list \
    --component seat-selection

  platform workload list \
    --component seat-selection

  platform catalog component creation get seat-selection

  platform catalog component clone seat-selection
```
