# aws_eip

|  |  |
|---|---|
| **Description** | Fixed public IP allocated for the NAT gateway. Created only when `enable_nat_gateway = true` — not created in the hub, since the hub has no NAT gateway either. |
| **Provider** | `terraform · aws` |
| **Type** | `EIP` |
| **Layer** | `02 · network-foundation` |
| **State** | `network-foundation` (not created there) / `control-plane` (created) |
| **Dependencies** | `None` directly (`domain = "vpc"`); paired 1:1 with `aws_nat_gateway.this` |
| **Produces** | Its allocation id, consumed by `aws_nat_gateway.this.allocation_id` |
| **Teardown** | After the NAT gateway releases it |

## Examples

- Gated by the same `var.enable_nat_gateway` flag as the NAT gateway itself — `count = var.enable_nat_gateway ? 1 : 0`. In the hub the count is `0`, so this resource does not exist there at all.
