# aws_lb_listener_rule

|  |  |
|---|---|
| **Status** | `Planned` — step `3.2`. No code exists yet. |
| **Description** | A host-header rule on the shared ALB's `:443` listener that routes one cell's traffic (`app.<id>.nonprod.<subzone>`) to that cell's target group. The hub scales by adding rules, not load balancers: N clients means one ALB plus N certificates plus N rules plus N target groups. |
| **Provider** | `terraform · aws.network` (aliased, hub side, lifecycle follows the cluster) |
| **Type** | `ALB listener rule` |
| **Layer** | `07 · ingress` |
| **State** | `control-plane (hub account, spoke lifecycle)` |
| **Dependencies** | The shared ALB's `:443` listener (from `connectivity/`), the cluster's wildcard certificate attached via `aws_lb_listener_certificate`, and `aws_lb_target_group.spoke` |
| **Produces** | Routing of `Host` matches to the cell's target group — the mechanism that fans out one shared ALB across every cluster |
| **Teardown** | Must go before the target group and certificate it references; going first avoids a moment where the rule exists but its target is already gone |

## Examples

- Quota that matters here: 100 rules per ALB (excluding the defaults) — looser than the 25-certificate ceiling, so certificates hit the limit first.
- Host-header matching is what variant (B) buys over a passthrough NLB at the hub: the ALB is L7 and can fan out by hostname, which a hub-side NLB (needed only for true end-to-end TLS) could not do.
