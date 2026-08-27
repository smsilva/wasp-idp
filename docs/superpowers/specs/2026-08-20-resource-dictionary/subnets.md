# subnets

|  |  |
|---|---|
| **Description** | Four subnets across two AZs: the public ones host NAT and external LBs; the private ones host nodes and pods.<br><br>Tagged so EKS can discover where to place LBs (`elb`/`internal-elb`).<br><br>Produce the per-role IDs consumed by the cluster and node-group. Held at teardown by `eks-node-group`. |
| **Provider** | provider-aws-ec2 |
| **Kind** | Subnet ×4 |
| **Layer** | 01 · network |
| **Dependencies** | `vpc` |
| **Produces** | `subnets` (per-role IDs) |
| **Teardown** | held by `eks-node-group` |

## Examples

- `public-1a` — us-east-1a, tag `kubernetes.io/role/elb`
- `public-1b` — us-east-1b, tag `kubernetes.io/role/elb`
- `private-1a` — us-east-1a, tag `kubernetes.io/role/internal-elb`
- `private-1b` — us-east-1b, tag `kubernetes.io/role/internal-elb`
