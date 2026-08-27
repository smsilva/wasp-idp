# nat-elastic-ip

|  |  |
|---|---|
| **Description** | Elastic IP: fixed public IPv4 address allocated to the NAT Gateway.<br><br>Gives a stable outbound IP to egress from the private subnets.<br><br>It is held on teardown by `eks-node-group` (the network only leaves after the nodes). |
| **Provider** | provider-aws-ec2 |
| **Kind** | EIP |
| **Layer** | 01 · network |
| **Dependencies** | None |
| **Teardown** | held by `eks-node-group` |
