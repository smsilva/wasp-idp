# aws_eks_addon

|  |  |
|---|---|
| **Description** | The two EKS-managed addons this cluster needs: `eks-pod-identity-agent` (the DaemonSet that serves Pod Identity credentials to every pod) and `aws-ebs-csi-driver` (persistent volume provisioning). No `service_account_role_arn` on either — the EBS CSI driver's identity comes from Pod Identity, configured at the root, not from IRSA. No `addon_version` pinned — AWS picks one compatible with the cluster's Kubernetes version. |
| **Provider** | `terraform · aws` |
| **Type** | `EKS Addon ×2` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | `aws_eks_cluster.this` (`cluster_name`) |
| **Produces** | Nothing consumed downstream as an attribute; its running DaemonSet is a runtime prerequisite for every Pod Identity association to actually deliver credentials |
| **Teardown** | Can be removed independently of node groups; typically torn down with the cluster |

## Examples

- Both addons are created together via `for_each` over `toset([...])`, with no explicit ordering between the two or against the Pod Identity associations — unlike the corporate-trail Crossplane chart, this layer's addon creation is not part of the race documented for the EBS CSI driver there; Pod Identity ordering here is enforced at the module level (association before Helm release), not at the addon level.
- `resolve_conflicts_on_create`/`resolve_conflicts_on_update = "OVERWRITE"` on both, so a re-apply after a manual `kubectl edit` on the addon's manifest does not get stuck fighting drift.
