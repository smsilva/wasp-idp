# records

|  |  |
|---|---|
| **Description** | The two DNS records that close resolution for the subzone: the `NS` delegation on the parent zone, and the `*.<zone>` A-alias pointing at the NLB.<br><br>The delegation makes the subzone resolvable on the internet; the wildcard routes any host (echo and apps) to the ingress.<br><br>The wildcard depends on the NLB hostname (via `nlb-hostname-observer`). |
| **Provider** | provider-aws-route53 |
| **Kind** | Record ×2 |
| **Layer** | 04 · dns |
| **Dependencies** | `route53-hosted-zone` |

## Examples

- `delegation` — NS on the parent zone (gate: nameServers published)
- `wildcard` — `*.<zone>` A-alias → NLB (needs `nlb-hostname-observer`)
