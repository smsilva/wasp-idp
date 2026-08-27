# aws_iam_role_policy_attachment

|  |  |
|---|---|
| **Description** | Attaches AWS-managed policies to the cluster role (`AmazonEKSClusterPolicy`), the node role (`AmazonEKSWorkerNodePolicy`, `AmazonEC2ContainerRegistryReadOnly`, `AmazonEKS_CNI_Policy`), and, for the EBS CSI Pod Identity role, `AmazonEBSCSIDriverPolicy`. |
| **Provider** | `terraform · aws` |
| **Type** | `IAM managed policy attachment` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | The `aws_iam_role` it attaches to (`cluster`, `node`, or a Pod Identity role) |
| **Produces** | Nothing consumed downstream as an attribute; `aws_eks_cluster.this` has an explicit `depends_on` on the cluster-role attachment so the role has its policy before EKS tries to use it |
| **Teardown** | Detached before its role can be deleted |

## Examples

- The node role's attachments use `for_each` over a `toset([...])` of three managed policy ARNs — one resource, three attachments.
- The cluster's `aws_eks_cluster.this` explicitly `depends_on`s `aws_iam_role_policy_attachment.cluster` — without it, Terraform could try to create the cluster before the policy attaches, and EKS would reject the role.
