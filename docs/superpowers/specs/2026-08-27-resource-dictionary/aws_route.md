# aws_route

|  |  |
|---|---|
| **Description** | Individual routes within this layer: `public_default` (`0.0.0.0/0` → the internet gateway, always created) and `private_default` (`0.0.0.0/0` → the NAT gateway, gated by `enable_nat_gateway`). Later layers add more `aws_route` resources of the same type pointing the supernet at a transit gateway. |
| **Provider** | `terraform · aws` |
| **Type** | `Route` |
| **Layer** | `02 · network-foundation` |
| **State** | `network-foundation` / `connectivity` / `control-plane` |
| **Dependencies** | `aws_route_table.public` + `aws_internet_gateway.this` (`public_default`); `aws_route_table.private` + `aws_nat_gateway.this[0]` (`private_default`) |
| **Produces** | Nothing consumed downstream within this layer |
| **Teardown** | Before its route table; the NAT-backed private route goes before the NAT gateway |

## Examples

- `private_default` is entirely absent in the hub (`enable_nat_gateway = false`): the private subnets have no default route at all until a TGW route is added in layer 04.
- The same resource type is reused for `aws_route.hub_to_tgw` (layer 04) and `aws_route.spoke_to_hub` (layer 05) — a different route, same Terraform type, in the private route table this layer creates.
