# nat-gateway

|  |  |
|---|---|
| **Description** | NAT Gateway: gives internet egress to resources in the private subnets (nodes and pods) without exposing them to ingress.<br><br>Lives in a public subnet and uses `nat-elastic-ip` as its outbound IP.<br><br>It is the target of the default route for the private route tables. |
| **Provider** | provider-aws-ec2 |
| **Kind** | NATGateway |
| **Layer** | 01 · network |
| **Dependencies** | `nat-elastic-ip`, `subnets/public-1a` |
| **Teardown** | held by `eks-node-group` |
