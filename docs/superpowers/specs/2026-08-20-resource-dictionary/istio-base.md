# istio-base

|  |  |
|---|---|
| **Description** | Installs the Istio CRDs and base resources (`Gateway`, `VirtualService`, etc.) in the cluster.<br><br>It is the foundation of the service mesh: `istiod` and `istio-ingress-gateway` depend on these CRDs existing first.<br><br>Runs no controllers — it only registers the types. |
| **Provider** | provider-helm |
| **Kind** | Release |
| **Layer** | 05 · platform |
| **Dependencies** | `provider-configs/helm` (gate: alb ready) |
