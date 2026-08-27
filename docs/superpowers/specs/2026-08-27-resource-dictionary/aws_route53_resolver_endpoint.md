# aws_route53_resolver_endpoint

|  |  |
|---|---|
| **Status** | **`Rejected`** (2026-08-27) — was step `2.4`, plan B. Plan A turned out impossible, but this one turned out **unnecessary**, which is the better reason not to build it. |
| **Description** | Would have been a Route 53 Resolver inbound endpoint in the spoke, with the Client VPN's `dns_servers` pointed at its IPs. Not needed: with the public endpoint disabled, "the cluster's API server endpoint **is resolved by public DNS servers to a private IP address** from the VPC" — resolution arrives from the DNS the operator already uses, at no cost and with no resource. Paying ~US$ 0.25/h (more than the EKS control plane) to solve a solved problem was the trap. Kept as a design record; the candidate returns if a future case needs a name that public DNS genuinely does not serve. |
| **Provider** | `terraform · aws` (spoke account, e.g. `control-plane`'s own provider) |
| **Type** | `Resolver inbound endpoint` |
| **Layer** | `06 · closing the endpoint` (rejected) |
| **State** | **rejected** — owns no state |
| **Dependencies** | The spoke VPC and its subnets (from `control-plane`'s `module.network`); reachability from the hub over the TGW |
| **Produces** | A pair of resolver IPs (one per AZ) that become the Client VPN endpoint's `dns_servers`, replacing the hub VPC's own resolver used under plan A |
| **Teardown** | Must be removed before the spoke VPC/subnets it lives in; any Client VPN config pointing `dns_servers` at it must be updated first, or DNS breaks for every connected operator |

## Examples

- Costs roughly US$ 0.25/h across two AZs — the price of not depending on a lookup that AWS can recreate underneath the repo at any cluster provision.
- Chosen as the fallback specifically because it does not depend on matching a hostname to find a zone the way plan A does — the resolver endpoint's identity is stable across cluster recreations.
