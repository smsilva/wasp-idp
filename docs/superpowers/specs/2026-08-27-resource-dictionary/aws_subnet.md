# aws_subnet

|  |  |
|---|---|
| **Description** | Two public and two private `/20`s, one pair per availability zone, derived from the VPC's CIDR with `cidrsubnet()` rather than hardcoded. Public subnets get `map_public_ip_on_launch` and the `kubernetes.io/role/elb` tag; private subnets get `kubernetes.io/role/internal-elb` — both used by the AWS Load Balancer Controller's subnet auto-discovery. |
| **Provider** | `terraform · aws` |
| **Type** | `Subnet ×4` |
| **Layer** | `02 · network-foundation` |
| **State** | `network-foundation` / `control-plane` (same module reused) |
| **Dependencies** | `aws_vpc.this` |
| **Produces** | `public_subnet_ids`, `private_subnet_ids`, `control_plane_subnet_ids` (all 4, concatenated) — the private ones are the EKS node group destination in `control-plane`; `control_plane_subnet_ids` is what EKS itself consumes there |
| **Teardown** | Before the VPC; after route table associations and anything placed in them (NAT gateway, node group ENIs) |

## Examples

- Exactly 2 AZs are required and validated: EKS demands at least 2 distinct AZs for its control plane, and that subnet list is immutable after cluster creation — changing AZs later means recreating the cluster.
- `subnet_newbits = 4` over a `/16` yields `/20`s (4094 usable IPs each), consuming 4 of the 16 available blocks and leaving 12 free; a `/24` would be too small once the VPC CNI starts handing pod IPs out of the node's subnet.
