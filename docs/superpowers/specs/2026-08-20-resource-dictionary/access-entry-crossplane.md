# access-entry-crossplane

|  |  |
|---|---|
| **Description** | Registers the Crossplane IAM principal (`crossplaneArn`) with the cluster's authentication API (EKS Access Entries).<br><br>It is the "who is it" half of the hub→spoke bridge: without this entry, the hub's Crossplane is not recognized by the new cluster's control plane.<br><br>The actual permission (the "what can it do") comes from `access-policy-crossplane`. |
| **Provider** | provider-aws-eks |
| **Kind** | AccessEntry |
| **Layer** | 03 · eks |
| **Dependencies** | `eks-cluster`, `crossplaneArn` (hub) |
