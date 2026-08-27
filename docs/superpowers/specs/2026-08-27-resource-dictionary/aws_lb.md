# aws_lb

|  |  |
|---|---|
| **Status** | `Planned` — step `3.1`. No code exists yet. |
| **Description** | The internal Network Load Balancer that sits inside the spoke, in front of the Istio ingress gateway. Its private IPs are fixed via `subnet_mapping` so the hub-side target group can point at them directly, without an ENI lookup. Cardinality is one per cluster, not one per Service. |
| **Provider** | `terraform · aws` (spoke account, `control-plane`) |
| **Type** | `Network Load Balancer` |
| **Layer** | `07 · ingress` |
| **State** | `control-plane` |
| **Dependencies** | The spoke's private subnets (`module.network`) and the fourth Pod Identity role (`module.pod_identity_lbc`) that lets the AWS Load Balancer Controller manage target group membership |
| **Produces** | Its two fixed private IPs, which feed `aws_lb_target_group.spoke` on the hub side; and its listener, which forwards to `aws_lb_target_group.istio` |
| **Teardown** | The `TargetGroupBinding` and gateway workload should go first (GitOps side); then this NLB, before the spoke's subnets/VPC |

## Examples

- `type = network`, internal — never exposed to the internet; the ALB in the hub is the only public entry point (decided: single ingress via the hub).
- Private IPs are fixed with `subnet_mapping { private_ipv4_address = cidrhost(<private subnet cidr>, 10) }` — deterministic, known at plan time, stable across recreations, avoiding the same class of fragile lookup as the `2.4` private-zone association.
- One NLB per cluster, not per Service: Istio's ingress gateway fans out to every app via `VirtualService`, so publishing a new app costs zero AWS resources.
- Costs roughly US$ 16/month.
