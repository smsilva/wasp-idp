# vpc

|  |  |
|---|---|
| **Description** | Isolated virtual network (CIDR `172.16.0.0/16`) that contains all of the environment's resources — subnets, gateways, nodes, and ENIs.<br><br>It is the root of the network layer: everything in L1 hangs off it.<br><br>Can only be deleted once everything else is gone, which is why it is held at teardown by `eks-node-group`. |
| **Provider** | provider-aws-ec2 |
| **Kind** | VPC |
| **Layer** | 01 · network |
| **Dependencies** | None (network root) |
| **Produces** | `vpcId` |
| **Teardown** | held by `eks-node-group` |
