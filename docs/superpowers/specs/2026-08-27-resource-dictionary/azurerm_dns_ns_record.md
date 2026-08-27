# azurerm_dns_ns_record

|  |  |
|---|---|
| **Description** | The delegation record in the parent zone, which lives in Azure DNS — the NS record that hands resolution of the nonprod subzone label over to the Route 53 name servers created in this same layer. |
| **Provider** | `terraform · azurerm` |
| **Type** | `Azure DNS NS record` |
| **Layer** | `03 · dns` |
| **State** | `dns` |
| **Dependencies** | `aws_route53_zone.subzone` (its `name_servers`) |
| **Produces** | The live delegation — the subzone becomes resolvable from the public internet |
| **Teardown** | Torn down with this root; removing it de-delegates the subzone without leaving name servers pointing at a zone that no longer exists |

## Examples

- The parent zone lives outside this repository's cloud of record — a rare case of an `azurerm` resource inside an otherwise-AWS root, needed because the apex domain was never migrated to Route 53.
- Gated by `var.manage_delegation`: turned off, this root never touches Azure at all, which matters because a root with two cloud providers fails `plan` for lack of credential on the second one even when the change only touches the first.
- Records come straight from `aws_route53_zone.subzone.name_servers` — no copy-paste of values between clouds, and destroying this root removes the NS record along with the zone reference, leaving no stale pointer.
- Short TTL (300s) on purpose: it is what lets a recreated subzone's new delegation take effect in minutes rather than hours.
