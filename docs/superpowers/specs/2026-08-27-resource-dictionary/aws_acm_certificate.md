# aws_acm_certificate

|  |  |
|---|---|
| **Description** | Public, DNS-validated certificate. In layer 04 it covers the Client VPN endpoint's hostname (`vpn.<subzone>`); the same resource type recurs in layer 05/07 for the cluster wildcard (`*.<id>.<subzone>`). No private key ever touches state or disk, and rotation is automatic — the client's `.ovpn` embeds Amazon's public CA chain, which does not change between issuances. |
| **Provider** | `terraform · aws` |
| **Type** | `ACM Certificate` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` (VPN certificate) / `control-plane` (cluster wildcard, layer 07) |
| **Dependencies** | `None` to request — `data.aws_route53_zone.subzone` (layer 03) is what lets `aws_route53_record.vpn_validation` prove ownership |
| **Produces** | `domain_validation_options` (record name/type/value to prove DNS ownership), `arn` — consumed by `aws_route53_record.vpn_validation` and, once validated, by `aws_ec2_client_vpn_endpoint.hub.server_certificate_arn` |
| **Teardown** | `create_before_destroy` — replaced before the old one is removed, so a recreate never leaves the VPN endpoint pointing at nothing |

## Examples

- Recreated nightly along with the rest of `connectivity` — this does not break existing client material, because what the `.ovpn` embeds is the public Amazon CA chain, not this leaf certificate.
- The certificate's domain name does not need to match the endpoint's connection hostname on purpose: the client uses `remote-cert-tls server`, which checks extended key usage, not the name — a name under the subzone is what makes DNS validation possible against a zone this root already controls.
- Indexed access to `domain_validation_options[0]` (not a `for_each` over the computed set) works only because there is exactly one domain and no SAN; adding a SAN later would require switching to a `for_each` driven by a list from configuration, not from the computed attribute.
