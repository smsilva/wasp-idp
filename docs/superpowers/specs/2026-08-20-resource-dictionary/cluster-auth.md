# cluster-auth

|  |  |
|---|---|
| **Description** | Generates access credentials for the EKS control plane and materializes them as a kubeconfig in a Secret (`<full>-kubeconfig`, `crossplane-system`).<br><br>It is the source of the hub→spoke bridge: the remote provider-configs (helm/kubernetes) read this Secret to operate inside the new cluster.<br><br>As long as Releases/Objects exist in the spoke, the Secret is held during teardown. |
| **Provider** | provider-aws-eks |
| **Kind** | ClusterAuth |
| **Layer** | 03 · eks |
| **Dependencies** | `eks-cluster` |
| **Produces** | Secret kubeconfig |
| **Teardown** | held by the `provider-configs` |
