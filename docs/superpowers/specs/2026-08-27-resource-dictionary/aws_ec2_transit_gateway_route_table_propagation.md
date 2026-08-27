# aws_ec2_transit_gateway_route_table_propagation

|  |  |
|---|---|
| **Description** | Advertises one side's attachment CIDR into the other side's TGW route table. Two instances close the round trip: `spoke_to_hub` (spoke's attachment → hub's table, so the hub learns the route back to this spoke) and `hub_to_spoke` (hub's attachment → the spoke's own tenant table, so the spoke learns the route to the hub and, behind it, to the Client VPN). |
| **Provider** | `terraform · aws.network` (aliased, hub side) |
| **Type** | `TGW route propagation ×2` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` (hub account, spoke lifecycle) |
| **Dependencies** | `spoke_to_hub`: `aws_ec2_transit_gateway_vpc_attachment.this` + `data.aws_ec2_transit_gateway_route_table.hub`, `depends_on aws_ec2_transit_gateway_vpc_attachment_accepter.this`. `hub_to_spoke`: `data.aws_ec2_transit_gateway_vpc_attachment.hub` + `aws_ec2_transit_gateway_route_table.spoke` |
| **Produces** | Nothing consumed as an attribute — its effect is routing state inside the TGW, a prerequisite for `aws_route.spoke_to_hub` to actually resolve traffic |
| **Teardown** | Removed with the attachment it propagates from; both must be gone before the tenant route table (`aws_ec2_transit_gateway_route_table.spoke`) can be deleted |

## Examples

- The two are NOT symmetric — one takes the spoke's attachment plus the hub's table, the other the hub's attachment plus the spoke's table. Swapping the two `transit_gateway_attachment_id`/`transit_gateway_route_table_id` pairs compiles fine and silently breaks routing in one direction only.
- Same shape of trap already documented for `aws_acm_certificate_validation` vs `aws_acm_certificate`: two references of the same type, easy to invert without a value-only assertion catching it — covered by a dedicated mutation test in this codebase.
- Without `hub_to_spoke`, the spoke never learns a route back to the hub, so the Client VPN tunnel (which terminates in the hub) can reach the hub but nothing beyond it.
