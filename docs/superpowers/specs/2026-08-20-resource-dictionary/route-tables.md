# route-tables

|  |  |
|---|---|
| **Description** | The VPC's two route tables — one for the public subnets, one for the private ones — which define the next hop for each subnet's traffic.<br><br>They receive the default route (`route-default`) to the IGW/NAT and are linked to the subnets by the `associations`. |
| **Provider** | provider-aws-ec2 |
| **Kind** | RouteTable ×2 |
| **Layer** | 01 · network |
| **Dependencies** | `vpc` |
| **Teardown** | held by `eks-node-group` |

## Examples

- `public` — default route to the `internet-gateway`
- `private` — default route to the `nat-gateway`
