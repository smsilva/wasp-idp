# target-group-binding

|  |  |
|---|---|
| **Status** | `Planned` — step `3.1`, cluster side. No code exists yet; lives in the GitOps repo, not this one. |
| **Description** | A custom resource of the AWS Load Balancer Controller that registers the Istio ingress gateway's pods into the Terraform-created `istio` target group. It is the one mechanism binding pods to a load balancer that Terraform, not the controller, created. |
| **Provider** | `— (GitOps)` |
| **Type** | `TargetGroupBinding` |
| **Layer** | `07 · ingress` |
| **State** | `— (GitOps repo)` |
| **Dependencies** | `aws_lb_target_group.istio` (its ARN, delivered via the `ingressTargetGroupArn` key in the `platform-bootstrap` ConfigMap) and the AWS Load Balancer Controller itself (installed via `module.pod_identity_lbc` + Helm) |
| **Produces** | Live membership of the gateway pods in the target group, which is what makes the spoke NLB actually forward traffic anywhere |
| **Teardown** | Should be removed (or its target pods drained) before the target group or NLB are destroyed, so the controller doesn't fight a disappearing target |

## Examples

- Exists specifically because the gateway Service is `ClusterIP`, not `LoadBalancer` — with `LoadBalancer` the controller would create its own NLB, and that NLB's ARN would only exist after the workload applied, breaking the single Terraform apply.
- One NLB per cluster, not per Service, is what this binding makes possible: every app behind the same gateway shares the same target group membership.
- Reads the target group ARN from the `platform-bootstrap` ConfigMap — the same Terraform → GitOps contract layer `05` already established, extended with one more key.
