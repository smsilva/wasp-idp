# Event flow

```text
                    ┌─> hello-alpha-db       (database)
hello-alpha ────────┼─> hello-alpha-uploads  (bucket)
                    └─> hello-alpha-events   (topic)
                               │ greeting.created, SNS → SQS
                               ▼
                         hello-beta-jobs     (queue) ──> hello-beta ──┬─> hello-beta-db      (database)
                                                                      └─> hello-beta-reports (bucket)
```

The only link between the two subdomains is the subscription of `hello-beta-jobs` to `hello-alpha-events`. In the catalog it is `hello-beta-jobs` → `dependsOn` → `hello-alpha-events`, which is what makes the graph cross from `notifier` into `greeter`.
