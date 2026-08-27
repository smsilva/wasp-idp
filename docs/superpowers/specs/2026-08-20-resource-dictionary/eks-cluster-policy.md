# eks-cluster-policy

|  |  |
|---|---|
| **Description** | Attaches `AmazonEKSClusterPolicy` (the permissions the control plane needs to manage AWS resources) to `eks-cluster-role`.<br><br>Without this attachment the cluster can't create/manage ENIs, LBs, and security groups on its behalf — control plane creation fails. |
| **Provider** | provider-aws-iam |
| **Kind** | RolePolicyAttachment |
| **Layer** | 02 · iam |
| **Dependencies** | `eks-cluster-role` |
