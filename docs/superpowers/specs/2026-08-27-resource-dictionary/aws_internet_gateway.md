# aws_internet_gateway

|  |  |
|---|---|
| **Description** | The VPC's door to the internet — attached unconditionally, even in the hub where nothing currently uses it for egress (only the public subnets' route table points at it). |
| **Provider** | `terraform · aws` |
| **Type** | `InternetGateway` |
| **Layer** | `02 · network-foundation` |
| **State** | `network-foundation` / `control-plane` (same module reused) |
| **Dependencies** | `aws_vpc.this` |
| **Produces** | Its id, consumed by `aws_route.public_default` and (via `depends_on`) required before `aws_nat_gateway.this` can allocate |
| **Teardown** | Must be detached before the VPC deletes; after the NAT gateway and public route |

## Examples

- AWS requires the IGW attached before a NAT gateway can be allocated, hence the explicit `depends_on = [aws_internet_gateway.this]` on `aws_nat_gateway.this` even though there is no direct attribute dependency between them.
