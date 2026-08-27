# aws_route53_zone_association

|  |  |
|---|---|
| **Status** | `Planned` — step `2.4`, plan A. No code exists yet. |
| **Description** | Associates the EKS API's private hosted zone (created and owned by AWS alongside the cluster's private endpoint) with the hub VPC, so the hostname resolves from inside the hub — where `terraform apply` and `kubectl` actually run. The free path, tried before the paid plan B (`aws_route53_resolver_endpoint`). |
| **Provider** | `terraform · aws.network` (aliased, hub side) — pairs with a `CreateVPCAssociationAuthorization` on the cluster account's side |
| **Type** | `Zone/VPC association` |
| **Layer** | `06 · private DNS` |
| **State** | `undecided` |
| **Dependencies** | The EKS cluster's private endpoint (produces the private hosted zone) and the hub VPC (from `network-foundation`) |
| **Produces** | Name resolution for the EKS API hostname from the hub VPC, which the Client VPN's `dns_servers` setting relies on |
| **Teardown** | Must be removed before (or alongside) the cluster whose zone it references; the zone itself is not this repository's to destroy — it is recreated by AWS on every cluster provision |

## Examples

- Risk called out in the design record: the private hosted zone is not an `aws_eks_cluster` output — finding it means a `data "aws_route53_zone"` lookup matching by the endpoint's hostname, which is fragile, and the zone is recreated on every cluster provision.
- Plan B if this trips: a Route 53 Resolver inbound endpoint in the spoke, at roughly US$ 0.25/h in two AZs — more robust and generalizes to N spokes, but not free.
- The two-sided authorization (`CreateVPCAssociationAuthorization` on the cluster account, `AssociateVPCWithHostedZone` on the hub account) is required because the zone and the VPC being associated live in different accounts.
