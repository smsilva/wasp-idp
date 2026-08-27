# aws_eks_node_group

|  |  |
|---|---|
| **Description** | The managed worker node pool(s) for the cluster, one per entry in `var.node_groups`. Named `<cluster_name>-<key>`, using the shared node role from `module.cluster` and the cell's private subnets. |
| **Provider** | `terraform · aws` |
| **Type** | `EKS NodeGroup` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | `var.cluster_name` / `var.node_role_arn` (from `module.cluster`), `var.subnet_ids` (from `module.network`, private subnets) |
| **Produces** | Running nodes, the prerequisite every `helm_release` and Pod Identity–backed workload needs to actually schedule; consumed as an implicit ordering dependency by `module.external_secrets`/`module.crossplane` via `depends_on = [module.nodegroup, ...]` |
| **Teardown** | Removed before the VPC/subnets it lives in (egress must survive until the pods are gone), and after every Helm release has been uninstalled through the API server |

## Examples

- `lifecycle { ignore_changes = [scaling_config[0].desired_size] }` — `desired_size` is left to the cluster autoscaler; Terraform does not fight it on every plan.
- Teardown order within layer 05 matters: Helm releases first (uninstall goes through the API server), then the node group, then `module.network` — reversing node group and network risks stranding ENIs mid-uninstall.
