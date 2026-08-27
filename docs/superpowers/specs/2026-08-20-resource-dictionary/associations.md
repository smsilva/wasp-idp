# associations

|  |  |
|---|---|
| **Description** | Link each of the 4 subnets to its route table (public or private), defining where that subnet's traffic exits through.<br><br>Without the association, the subnet uses the VPC's default route table (no egress route) — nodes in the private subnets would not reach the NAT. |
| **Provider** | provider-aws-ec2 |
| **Kind** | RouteTableAssociation ×4 |
| **Layer** | 01 · network |
| **Dependencies** | route-table + subnet |
| **Teardown** | held by `eks-node-group` |

## Examples

- `public-1a` → `route-tables/public`
- `public-1b` → `route-tables/public`
- `private-1a` → `route-tables/private`
- `private-1b` → `route-tables/private`
