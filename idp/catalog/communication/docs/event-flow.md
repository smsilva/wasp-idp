# Event flow

```text
                     ┌─> greeting-db       (database)
greeting-api ────────┼─> greeting-avatars  (bucket)
                     └─> greeting-events   (topic)
                               │ greeting.created, topic → queue
                               ▼
                         notification-jobs (queue) ──> notification-api ──┬─> notification-db      (database)
                                                                          └─> notification-reports (bucket)
```

The only link between the two subdomains is the subscription of `notification-jobs` to `greeting-events`. In the catalog it is `notification-jobs` → `dependsOn` → `greeting-events`, which is what makes the graph cross from `notifier` into `greeter`.
