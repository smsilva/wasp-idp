# internet-gateway

|  |  |
|---|---|
| **Description** | Internet Gateway: the VPC's door to the public internet (ingress and egress for the public subnets).<br><br>It is the target of the default route for the public subnets (where NAT and external LBs live).<br><br>Without it, nothing in the VPC reaches the internet directly. |
| **Provider** | provider-aws-ec2 |
| **Kind** | InternetGateway |
| **Layer** | 01 · network |
| **Dependencies** | `vpc` |
| **Teardown** | held by `eks-node-group` |
