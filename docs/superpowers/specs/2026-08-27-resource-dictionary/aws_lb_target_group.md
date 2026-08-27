# aws_lb_target_group

|  |  |
|---|---|
| **Status** | `Planned` — one instance in step `3.1`, one in step `3.2`. No code exists yet. |
| **Description** | Two distinct `type = ip` target groups, at opposite ends of the ingress path. The spoke-side one (`istio`) is what the Istio gateway pods register into via `TargetGroupBinding`. The hub-side one (`spoke`) holds the spoke NLB's fixed private IPs, so the hub ALB can reach into the spoke without crossing accounts at runtime. |
| **Provider** | `istio` target group: `terraform · aws` (spoke account, `control-plane`). `spoke` target group: `terraform · aws.network` (aliased, hub side, lifecycle follows the cluster) |
| **Type** | `Target group` (`type = ip`) ×2 |
| **Layer** | `07 · ingress` |
| **State** | `control-plane` for both — the hub-side one lives in the spoke's state via the aliased provider, per the lifecycle-follows-the-cell rule |
| **Dependencies** | `istio`: the spoke NLB's listener. `spoke`: `aws_lb.internal`'s fixed private IPs |
| **Produces** | `istio`: its ARN goes into the `platform-bootstrap` ConfigMap as `ingressTargetGroupArn`, consumed by the GitOps-side `TargetGroupBinding`. `spoke`: consumed by `aws_lb_listener_rule.spoke` on the shared ALB |
| **Teardown** | `istio`: the `TargetGroupBinding` and gateway pods must deregister first. `spoke`: the listener rule referencing it must go first |

## Examples

- Both are `type = ip`, not `instance` — required because targets are pod IPs (`istio`) or the NLB's fixed private IPs (`spoke`), neither of which is an EC2 instance.
- The 25-certificates-per-ALB quota (shared with `aws_lb_listener_certificate`) is what actually bounds how many spoke target groups can share one ALB, not a target-group-specific quota.
- Choosing variant (B) over "ALB straight to pod IPs via TGW" avoided registering pod IPs (which churn every deploy) into a target group living in a different account from the pods.
