# Communication

Everything that sends a message to someone: the greetings produced by `hello-alpha` and the notifications `hello-beta` derives from them.

This page is an example of documentation that lives **in the IDP repository**, next to the catalog file that declares the domain (`idp/catalog/communication/`). The services keep their own docs in their own repositories — see the *Docs* tab of `hello-alpha` and `hello-beta`.

| Subdomain | Owner | System | Component |
|---|---|---|---|
| `messaging` | `team-alpha` | `greeter` | `hello-alpha` |
| `notifications` | `team-beta` | `notifier` | `hello-beta` |

The databases, queue, topic and buckets in this domain are catalog entries only. Nothing provisions them.
