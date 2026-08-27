# aws_route_table

|  |  |
|---|---|
| **Description** | The `public` and `private` route tables of a VPC — one of each, shared by all subnets of that type rather than one per subnet. The private table is the one layer 04/05 attach a TGW route into. |
| **Provider** | `terraform · aws` |
| **Type** | `RouteTable ×2` |
| **Layer** | `02 · network-foundation` |
| **State** | `network-foundation` / `control-plane` (same module reused) |
| **Dependencies** | `aws_vpc.this` |
| **Produces** | `private_route_table_id` (the module output) — the address any later TGW attachment's route (`aws_route.hub_to_tgw`, `aws_route.spoke_to_hub`) is inserted into |
| **Teardown** | After its routes and associations; before the VPC |

## Examples

- The private route table is deliberately singular and shared, not per-subnet: whoever attaches a TGW route references this one table, not four separate ones.
