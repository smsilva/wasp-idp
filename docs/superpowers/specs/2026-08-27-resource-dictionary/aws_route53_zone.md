# aws_route53_zone

|  |  |
|---|---|
| **Description** | The delegated nonprod subzone under the parent domain (which lives in Azure DNS). Every cluster and app name in this environment hangs off it — it is the boundary of DNS blast radius: external-dns inside a cluster is scoped to this zone and nothing else. |
| **Provider** | `terraform · aws` |
| **Type** | `Route 53 Zone` |
| **Layer** | `03 · dns` |
| **State** | `dns` |
| **Dependencies** | `None` |
| **Produces** | `subzone_name` (FQDN), `subzone_id` (zone id), `subzone_name_servers` — consumed by `azurerm_dns_ns_record.delegation` in this same layer, and by every later ACM/Route53 record that validates by DNS in this zone |
| **Teardown** | `Permanent (prevent_destroy)` |

## Examples

- Guarded with `prevent_destroy` because destroying it loses the name servers and breaks the parent's delegation until a new NS record propagates — unlike the connectivity layer, which is destroyed nightly on purpose.
- Kept in its own root rather than inside `connectivity/`: that layer is torn down every night, and a recreated zone would get new name servers, causing intermittent breakage during NS propagation.
- Only `~US$ 0.50/month` — cheap enough that permanence costs nothing, unlike the NAT gateway it deliberately avoids.
