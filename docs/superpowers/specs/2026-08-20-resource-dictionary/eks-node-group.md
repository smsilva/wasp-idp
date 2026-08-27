# eks-node-group

|  |  |
|---|---|
| **Description** | Managed node group: pool of EC2 instances (t3.medium) in the private subnets that run the pods.<br><br>Besides providing capacity, on teardown it's the `by` that holds all of the L1a network (VPC, subnets, IGW, NAT) until pods and ENIs leave — preventing network orphans. |
| **Provider** | provider-aws-eks |
| **Kind** | NodeGroup |
| **Layer** | 03 · eks |
| **Dependencies** | `eks-cluster`, `eks-node-role`, `subnets` (private) |
| **Teardown** | it's the `by` that holds the L1a network until the pods leave |
