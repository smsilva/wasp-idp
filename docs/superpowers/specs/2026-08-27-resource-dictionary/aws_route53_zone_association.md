# aws_route53_zone_association

|  |  |
|---|---|
| **Status** | **`Rejected`** (2026-08-27) — was step `2.4`, plan A. Not fragile: **impossible**. No code will exist. |
| **Description** | Would have associated the EKS API's private hosted zone with the hub VPC, so the hostname resolved from inside the hub — where `terraform apply` and `kubectl` actually run. It cannot be done, because the zone is invisible: "Amazon EKS creates a Route 53 private hosted zone on your behalf and associates it with your cluster's VPC. This private hosted zone is **managed by Amazon EKS, and it doesn't appear in your account's Route 53 resources**." There is no `zone_id` to read and nothing to authorize — one cannot authorize association of a zone one does not own. Kept as a design record; see [aws_vpc_security_group_ingress_rule](aws_vpc_security_group_ingress_rule.md) for what step `2.4` actually became. |
| **Provider** | `terraform · aws.network` (aliased, hub side) — pairs with a `CreateVPCAssociationAuthorization` on the cluster account's side |
| **Type** | `Zone/VPC association` |
| **Layer** | `06 · closing the endpoint` (rejected) |
| **State** | **rejected** — owns no state |
| **Dependencies** | The EKS cluster's private endpoint (produces the private hosted zone) and the hub VPC (from `network-foundation`) |
| **Produces** | Name resolution for the EKS API hostname from the hub VPC, which the Client VPN's `dns_servers` setting relies on |
| **Teardown** | Must be removed before (or alongside) the cluster whose zone it references; the zone itself is not this repository's to destroy — it is recreated by AWS on every cluster provision |

## Examples

- Risk called out in the design record: the private hosted zone is not an `aws_eks_cluster` output — finding it means a `data "aws_route53_zone"` lookup matching by the endpoint's hostname, which is fragile, and the zone is recreated on every cluster provision.
- Plan B if this trips: a Route 53 Resolver inbound endpoint in the spoke, at roughly US$ 0.25/h in two AZs — more robust and generalizes to N spokes, but not free.
- The two-sided authorization (`CreateVPCAssociationAuthorization` on the cluster account, `AssociateVPCWithHostedZone` on the hub account) is required because the zone and the VPC being associated live in different accounts.
