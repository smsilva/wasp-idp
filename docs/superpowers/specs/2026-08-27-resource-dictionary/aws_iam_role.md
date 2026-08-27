# aws_iam_role

|  |  |
|---|---|
| **Description** | Every IAM role this layer creates: the EKS cluster role, the shared node role, and one per Pod Identity consumer (EBS CSI driver, External Secrets, Crossplane, and later the load balancer controller). Each carries its own trust policy — `eks.amazonaws.com`, `ec2.amazonaws.com`, or `pods.eks.amazonaws.com` for the Pod Identity roles. |
| **Provider** | `terraform · aws` |
| **Type** | `IAM Role ×N` (`cluster`, `node`, one per Pod Identity module instance) |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | `None` for `cluster`/`node` (roots of `module.cluster`); each Pod Identity role is root of its own `module.pod_identity_*` instance |
| **Produces** | `arn`, `name` — consumed by `aws_iam_role_policy_attachment`, `aws_iam_role_policy`, `aws_eks_cluster.this.role_arn`, `module.nodegroup` (`node_role_arn`), and `aws_eks_pod_identity_association.this.role_arn` |
| **Teardown** | Only after every attachment/inline policy and, for Pod Identity roles, the association and the workload consuming it are gone |

## Examples

- Pod Identity trust policies require both `sts:AssumeRole` and `sts:TagSession` — missing `TagSession` produces an `AccessDenied` with no useful message pointing at the cause.
- The node role is shared by every node group; per-workload permissions come from Pod Identity, not from the node role — this is the whole point of the layer.
- Trust policies are built with `jsonencode(...)` rather than `data.aws_iam_policy_document`, because under `mock_provider` the data source returns a synthetic value that breaks assertions on the real trust document.
