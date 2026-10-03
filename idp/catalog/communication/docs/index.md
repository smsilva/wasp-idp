# Communication

Everything that sends a message to someone: the greetings produced by `greeting-api` and the notifications `notification-api` derives from them.

This page is an example of documentation that lives **in the IDP repository**, next to the catalog file that declares the domain (`idp/catalog/communication/`). The services keep their own docs in their own repositories — see the *Docs* tab of `greeting-api` and `notification-api`.

| Subdomain | Owner | System | Component |
|---|---|---|---|
| `messaging` | `team-alpha` | `greeter` | `greeting-api` |
| `notifications` | `team-beta` | `notifier` | `notification-api` |

The databases, queue, topic and buckets in this domain are catalog entries only. Nothing provisions them.
