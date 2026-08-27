# aws_route_table_association

|  |  |
|---|---|
| **Description** | Binds each of the 4 subnets to its route table — 2 public subnets to `aws_route_table.public`, 2 private subnets to `aws_route_table.private`. |
| **Provider** | `terraform · aws` |
| **Type** | `RouteTableAssociation ×4` |
| **Layer** | `02 · network-foundation` |
| **State** | `network-foundation` / `control-plane` (same module reused) |
| **Dependencies** | `aws_subnet.public[*]` / `aws_subnet.private[*]`, `aws_route_table.public` / `aws_route_table.private` |
| **Produces** | Nothing consumed downstream |
| **Teardown** | Before its subnet and before its route table |
