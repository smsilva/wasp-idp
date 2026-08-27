# access-policy-crossplane

|  |  |
|---|---|
| **Description** | Grants the Crossplane principal the `AmazonEKSClusterAdminPolicy` scoped to the cluster (EKS Access Policy).<br><br>It is the "what can it do" half of the hub→spoke bridge — it depends on `access-entry-crossplane` existing first.<br><br>Together, they let the hub's Crossplane install Releases/Objects inside the spoke via the remote provider-configs. |
| **Provider** | provider-aws-eks |
| **Kind** | AccessPolicyAssociation |
| **Layer** | 03 · eks |
| **Dependencies** | `access-entry-crossplane`, `crossplaneArn` (hub) |
