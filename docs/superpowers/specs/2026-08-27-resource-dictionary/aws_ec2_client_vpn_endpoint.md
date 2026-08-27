# aws_ec2_client_vpn_endpoint

|  |  |
|---|---|
| **Description** | The maintenance tunnel into the private network, federated through SAML via Identity Center. Split-tunnel (`split_tunnel = true`), so only the supernet is routed through it — an operator's other traffic is unaffected. It performs SNAT: traffic that reaches a spoke arrives with a source IP from the hub VPC's CIDR, not from the client CIDR block. |
| **Provider** | `terraform · aws` (account `network`) |
| **Type** | `Client VPN endpoint` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` |
| **Dependencies** | `aws_acm_certificate_validation.vpn` (`server_certificate_arn` — not the certificate directly, so the endpoint cannot be created against a still-`PENDING_VALIDATION` cert), `data.aws_vpc.hub` (`vpc_id`), `aws_iam_saml_provider.client_vpn` (`authentication_options.saml_provider_arn`) |
| **Produces** | `id` — consumed by `aws_ec2_client_vpn_network_association`, `aws_ec2_client_vpn_route`, `aws_ec2_client_vpn_authorization_rule`; and its DNS name, an output of the layer |
| **Teardown** | Every network association must go first (each takes ~7–10 minutes), then routes and authorization rules; destroying the endpoint changes its DNS name, so distributed client profiles need reissuing |

## Examples

- `vpc_id` is deliberately the hub VPC, not a `transit_gateway_configuration` block on the endpoint itself — that alternative attachment path takes hours to tear down and would block deleting the transit gateway.
- Connection logging (`connection_log_options { enabled = false }`) is off by default — no audit trail of who connected when; a hardening item, not an operability gap.
- `authorize_all_groups` is never set on the associated authorization rules — doing so would collapse per-group isolation, the entire point of choosing SAML over mutual-auth certificates.
