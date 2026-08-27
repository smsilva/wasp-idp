# aws_lb_listener_certificate

|  |  |
|---|---|
| **Status** | `Planned` — step `3.2`. No code exists yet. |
| **Description** | Attaches a cluster's ACM wildcard certificate (`*.<id>.nonprod.<subzone>`) to the shared ALB's `:443` listener by SNI, alongside every other cluster's certificate on the same listener. The 25-certificates-per-ALB service quota is what actually limits how many cells can share one ALB. |
| **Provider** | `terraform · aws.network` (aliased, hub side, lifecycle follows the cluster) |
| **Type** | `ALB listener certificate` |
| **Layer** | `07 · ingress` |
| **State** | `control-plane (hub account, spoke lifecycle)` |
| **Dependencies** | `aws_acm_certificate_validation.cluster` (DNS-validated wildcard cert) and the shared ALB's `:443` listener |
| **Produces** | SNI-based TLS termination for the cell's hostname at the edge; enables `aws_lb_listener_rule.spoke` to match traffic that already terminated correctly |
| **Teardown** | Must be detached before the certificate itself, and before the listener rule that depends on this hostname being served with valid TLS |

## Examples

- TLS terminates at the ALB; the ALB does not validate the backend's certificate, so the NLB → gateway hop can be plain HTTP or a self-signed cert without weakening the edge.
- Certificates are per-cluster wildcards (`*.<id>.nonprod.<subzone>`), not per-app — one certificate covers every app hostname under that cluster's single level of wildcarding.
- Renewal is automatic via ACM DNS validation as long as the validation CNAME stays in the zone — no cert-manager DNS-01 challenge per cluster, and no Let's Encrypt rate-limit exposure.
