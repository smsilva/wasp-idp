# istio-ingressgateway-service

|  |  |
|---|---|
| **Status** | `Planned` — step `3.1`, cluster side. No code exists yet; lives in the GitOps repo, not this one. |
| **Description** | The Kubernetes Service fronting Istio's ingress gateway pods, deliberately typed `ClusterIP` rather than `LoadBalancer`. The NLB is Terraform's, created ahead of any workload; if the Service were `LoadBalancer`, the AWS Load Balancer Controller would create its own NLB whose ARN would only exist after the workload applied, breaking the single-apply acceptance criterion. |
| **Provider** | `— (GitOps)` |
| **Type** | `Service (ClusterIP)` |
| **Layer** | `07 · ingress` |
| **State** | `— (GitOps repo)` |
| **Dependencies** | The Istio ingress gateway Helm install itself; conceptually pairs with `aws_lb.internal` (Terraform-created NLB) and `target-group-binding` for the actual traffic path |
| **Produces** | The pod selector that `target-group-binding` uses to know which pods to register; ultimately what an `Gateway` + `VirtualService` route traffic into |
| **Teardown** | Independent of Terraform's NLB lifecycle; can be removed with the rest of the GitOps-managed workload without touching AWS resources |

## Examples

- Cardinality × churn is the argument recorded for this shape: the NLB is infrastructure (cardinality 1 per cluster, never changes), so it is Terraform's; the gateway Service is workload, so it is GitOps's, but it must not be the thing that creates the NLB.
- Publishing a new app under this gateway is only a `VirtualService` — zero AWS resources, zero cost, zero `terraform apply`.
- Lives in the `wasp-gitops` repo on a branch dedicated to this experiment; this repository does not gain a GitOps directory of its own.
