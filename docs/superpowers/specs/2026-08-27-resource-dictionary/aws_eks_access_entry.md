# aws_eks_access_entry

|  |  |
|---|---|
| **Description** | Registers an IAM principal with the EKS cluster's API-based access control, replacing the legacy `aws-auth` ConfigMap. One per entry in `var.access_entries` (gate: the map is empty by default). |
| **Provider** | `terraform · aws` |
| **Type** | `EKS access entry` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | `aws_eks_cluster.this` (`cluster_name`) |
| **Produces** | Implicit identity (`cluster_name` + `principal_arn`) consumed by `aws_eks_access_policy_association.this`, which `depends_on` this resource explicitly |
| **Teardown** | Its policy association must be removed first |

## Examples

- The EKS API rejects a policy association for a principal that has no access entry yet — hence the explicit `depends_on` on `aws_eks_access_policy_association.this`, rather than relying on the implicit reference alone.
- With `authentication_mode = "API"` and no `bootstrapClusterCreatorAdminPermissions` disabled here, this mechanism is additive to the creator's automatic admin, not a replacement for it in this cluster.
