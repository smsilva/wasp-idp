# kubernetes_config_map_v1

|  |  |
|---|---|
| **Description** | `platform-bootstrap`, in `crossplane-system` — the contract Terraform hands to GitOps. Everything the app-of-apps needs to know about this cell (region, cluster name, hub VPC id, spoke subnet ids, the Crossplane Pod Identity role ARN, the network account id, and the list of target account ids) so no GitOps manifest hardcodes an account or VPC id. |
| **Provider** | `terraform · kubernetes` |
| **Type** | `ConfigMap` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | `data.aws_vpc.hub`, `module.network`, `module.cluster`, `module.pod_identity_crossplane`, `var.network_account_id`, `var.target_account_ids`, `depends_on = [module.crossplane]` |
| **Produces** | `region`, `clusterName`, `hubVpcId`, `spokeSubnetIds`, `crossplaneRoleArn`, `networkAccountId`, `targetAccountIds` — read by GitOps, not by any other Terraform resource |
| **Teardown** | No dependents within Terraform; removed with the `crossplane-system` namespace / cluster |

## Examples

- `platform-bootstrap` is a `resource`, never a `data` source — a data source on the `kubernetes`/`helm` providers would be evaluated during `plan`, before the cluster (and thus the provider's endpoint) exists; only a resource defers correctly to apply time.
- It `depends_on`s `module.crossplane`, so GitOps never reads a ConfigMap that predates the namespace or the release it describes.
- Lists (`spokeSubnetIds`, `targetAccountIds`) are flattened with `join(",", ...)` because Kubernetes ConfigMap `data` values are strings, not lists.
