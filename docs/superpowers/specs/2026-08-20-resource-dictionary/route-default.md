# route-default

|  |  |
|---|---|
| **Description** | The default `0.0.0.0/0` route of each route-table, pointing to the right gateway: public → internet-gateway, private → nat-gateway.<br><br>It is what gives internet egress — without it the subnets are isolated.<br><br>Held at teardown by `eks-node-group`. |
| **Provider** | provider-aws-ec2 |
| **Kind** | Route ×2 |
| **Layer** | 01 · network |
| **Dependencies** | the route-table + the target gateway |
| **Teardown** | held by `eks-node-group` |

## Examples

- `public` → `internet-gateway`
- `private` → `nat-gateway`
