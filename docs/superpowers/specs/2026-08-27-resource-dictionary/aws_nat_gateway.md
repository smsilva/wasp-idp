# aws_nat_gateway

|  |  |
|---|---|
| **Description** | Egress for the private subnets, placed in the first public subnet (a NAT in a private subnet cannot reach the internet gateway). Gated off in the hub: `enable_nat_gateway = false`, since nothing routes through the hub until a TGW exists, and turning it on would bill roughly US$ 32/month for zero traffic. |
| **Provider** | `terraform · aws` |
| **Type** | `NATGateway` |
| **Layer** | `02 · network-foundation` |
| **State** | `network-foundation` (not created there) / `control-plane` (created) |
| **Dependencies** | `aws_eip.nat[0]`, `aws_subnet.public[0]`, `aws_internet_gateway.this` (explicit `depends_on`, since AWS requires the IGW attached first) |
| **Produces** | Its id, consumed by `aws_route.private_default[0].nat_gateway_id` |
| **Teardown** | Before its EIP and before the public subnet it sits in; the private default route goes first |

## Examples

- Not created in the hub — the module's `enable_nat_gateway` flag is the single switch that keeps `network-foundation` at zero recurring cost while still being the exact module `control-plane` reuses with NAT turned on.
