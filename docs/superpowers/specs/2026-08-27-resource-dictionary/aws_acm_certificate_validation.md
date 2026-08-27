# aws_acm_certificate_validation

|  |  |
|---|---|
| **Description** | Blocks until the referenced certificate transitions to `ISSUED` — resolves in ~1 second once the DNS validation record already exists and has propagated, but without it a certificate could be handed to a consumer while still `PENDING_VALIDATION`, and the failure would surface at connection time instead of at apply time. |
| **Provider** | `terraform · aws` |
| **Type** | `ACM validation` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` (VPN certificate) / `control-plane` (cluster wildcard, layer 07) |
| **Dependencies** | `aws_acm_certificate.vpn`, `aws_route53_record.vpn_validation` (via `validation_record_fqdns`) |
| **Produces** | `certificate_arn` — consumed by `aws_ec2_client_vpn_endpoint.hub.server_certificate_arn` (layer 04) or `aws_lb_listener_certificate` (layer 07) |
| **Teardown** | Torn down with the certificate it validates; no independent lifecycle |

## Examples

- This resource is the reason the certificate cannot be handed to a consumer half-issued — without it, `aws_ec2_client_vpn_endpoint` could reference a `PENDING_VALIDATION` ARN and the apply would succeed while the tunnel silently fails to serve TLS.
- A `terraform_remote_state` shortcut is never used to feed `validation_record_fqdns` — the FQDN comes from the same root's own `aws_route53_record`, keeping the two in lockstep even if the certificate and record are ever recreated together.
- A mutation test proved this matters: swapping which resource's attribute feeds `validation_record_fqdns` for a different resource with the same computed value did not fail any value-based assertion — ordering is an edge of the dependency graph, not a value, and needs its own explicit test.
