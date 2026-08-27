# aws_eks_access_policy_association

|  |  |
|---|---|
| **Description** | Grants an access entry one of the EKS-managed access policies (e.g. cluster-admin), scoped by `access_scope { type = ... }` (`cluster` or `namespace`). One per entry in `var.access_entries`. |
| **Provider** | `terraform · aws` |
| **Type** | `EKS access policy association` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | `aws_eks_cluster.this`, `depends_on aws_eks_access_entry.this` (the API demands the entry exist first) |
| **Produces** | The RBAC grant itself — nothing consumed as a Terraform attribute downstream |
| **Teardown** | Removed before its access entry |

## Examples

- Access entries replace `aws-auth`, and the API requires the entry before its policy association — `depends_on` here is not optional convenience, the create call fails without it.
- `access_scope` defaults to `"cluster"` in the module's variable type (`optional(string, "cluster")`), so a caller only needs to set it explicitly for a namespace-scoped grant.
