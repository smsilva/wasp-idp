# route53-hosted-zone

|  |  |
|---|---|
| **Description** | DNS subzone dedicated to the cluster (`<name>.<domainSuffix>`), created with `forceDestroy` so it exits cleanly at teardown.<br><br>It is the environment's isolated DNS namespace.<br><br>Produces the `zoneId` (where records are created) and the `nameServers` (published on the parent zone by the delegation). |
| **Provider** | provider-aws-route53 |
| **Kind** | Zone |
| **Layer** | 04 · dns |
| **Dependencies** | None |
| **Produces** | `zoneId`, `nameServers` |
