# aws_eks_cluster

|  |  |
|---|---|
| **Description** | The managed EKS control plane for this cell, `authentication_mode = "API"` with `bootstrap_cluster_creator_admin_permissions = true`, running in the cell's own public+private subnets (`module.network`, `10.2.0.0/16` here). Kubernetes version defaults to `1.36`. |
| **Provider** | `terraform · aws` |
| **Type** | `EKS Cluster` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | `aws_iam_role.cluster` (`role_arn`), `depends_on aws_iam_role_policy_attachment.cluster`, `module.network` (`control_plane_subnet_ids`) |
| **Produces** | `name`, `endpoint`, `certificate_authority[0].data`, `vpc_config[0].cluster_security_group_id`, `identity[0].oidc[0].issuer` — consumed by `aws_eks_access_entry`, `aws_eks_access_policy_association`, `aws_eks_addon`, `module.nodegroup`, every `aws_eks_pod_identity_association`, and the `kubernetes`/`helm` provider blocks in `providers.tf` |
| **Teardown** | Every node group, addon, access entry/association and Pod Identity association must be gone first; `subnet_ids` is immutable after creation |

## Examples

- Unlike the chart's cluster (via Crossplane), this cluster's creator DOES get automatic cluster-admin (`bootstrap_cluster_creator_admin_permissions = true`) — no separate access entry needed for the applying identity, because `cicd`'s profile has direct admin.
- `public_access_cidrs` empty is read by the AWS API as `0.0.0.0/0`; the module's own variable validation refuses an empty list whenever `endpoint_public_access` is true, so the API's ambiguity never reaches this resource.
- The `kubernetes` and `helm` providers in the same root are configured from this resource's own `endpoint`/`certificate_authority` outputs — one `terraform apply` spans all three providers, with no `-target`.
