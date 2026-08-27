# node-policies

|  |  |
|---|---|
| **Description** | Attaches to the `eks-node-role` the three managed policies an EKS node needs: registering with the cluster (worker), pulling images from ECR, and operating the CNI network.<br><br>Without them, nodes never become `Ready` nor run pods with network. |
| **Provider** | provider-aws-iam |
| **Kind** | RolePolicyAttachment ×3 |
| **Layer** | 02 · iam |
| **Dependencies** | `eks-node-role` |

## Examples

- `worker` — AmazonEKSWorkerNodePolicy
- `ecr` — AmazonEC2ContainerRegistryReadOnly
- `cni` — AmazonEKS_CNI_Policy
