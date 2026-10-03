# Greeter

System of the `messaging` subdomain, owned by `team-alpha`.

| Entity | Kind | Role |
|---|---|---|
| `hello-alpha` | Component | HTTP service that answers greetings |
| `hello-alpha-db` | Resource (database) | Stores every greeting |
| `hello-alpha-events` | Resource (topic) | One `greeting.created` event per greeting |
| `hello-alpha-uploads` | Resource (bucket) | Avatar images attached to greetings |

## Contract with notifier

`greeting.created` is the public contract of this system. Its only known consumer is the `hello-beta-jobs` queue of the `notifier` system. A change to the event payload needs a heads-up to `team-beta`.

A `System` can point its `backstage.io/techdocs-ref` at a subdirectory (`dir:./greeter`), which is how this page sits next to the domain docs without mixing with them.
