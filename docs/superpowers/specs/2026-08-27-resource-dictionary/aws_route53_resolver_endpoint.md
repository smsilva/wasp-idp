# aws_route53_resolver_endpoint

|  |  |
|---|---|
| **Status** | `Planned` — step `2.4`, plan B, only if plan A (`aws_route53_zone_association`) does not hold up. No code exists yet. |
| **Description** | A Route 53 Resolver inbound endpoint in the spoke, so the hub can resolve the EKS API's private hostname by pointing the Client VPN's `dns_servers` at the endpoint's IPs instead of relying on a fragile private-zone association. More robust and generalizes to N spokes; not free. |
| **Provider** | `terraform · aws` (spoke account, e.g. `control-plane`'s own provider) |
| **Type** | `Resolver inbound endpoint` |
| **Layer** | `06 · private DNS` |
| **State** | `undecided` |
| **Dependencies** | The spoke VPC and its subnets (from `control-plane`'s `module.network`); reachability from the hub over the TGW |
| **Produces** | A pair of resolver IPs (one per AZ) that become the Client VPN endpoint's `dns_servers`, replacing the hub VPC's own resolver used under plan A |
| **Teardown** | Must be removed before the spoke VPC/subnets it lives in; any Client VPN config pointing `dns_servers` at it must be updated first, or DNS breaks for every connected operator |

## Examples

- Costs roughly US$ 0.25/h across two AZs — the price of not depending on a lookup that AWS can recreate underneath the repo at any cluster provision.
- Chosen as the fallback specifically because it does not depend on matching a hostname to find a zone the way plan A does — the resolver endpoint's identity is stable across cluster recreations.
