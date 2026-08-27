# eks-cluster

|  |  |
|---|---|
| **Description** | Managed EKS control plane (Kubernetes v1.34), distributed across 4 subnets (2 AZs).<br><br>It's the anchor of the eks layer: node-group, addons, and the hub→spoke bridge reference this cluster.<br><br>Takes ~12-15 min to become active — it's the bottleneck of provisioning. |
| **Provider** | provider-aws-eks |
| **Kind** | Cluster |
| **Layer** | 03 · eks |
| **Dependencies** | `eks-cluster-role`, `subnets` |
| **Produces** | the cluster (anchors node-group, addons, and the bridge) |
