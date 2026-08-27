# saml-application

|  |  |
|---|---|
| **Description** | An Identity Center application registered for the Client VPN, whose SAML metadata XML is exported and consumed by `aws_iam_saml_provider` in layer 04 (connectivity). It is what lets a human operator authenticate to the maintenance tunnel through the same federated identity used everywhere else, instead of a per-VPN local user. |
| **Provider** | `console` (no CLI/Terraform path documented for this step) |
| **Type** | `Identity Center application` |
| **Layer** | `00 · accounts` |
| **State** | `—` |
| **Dependencies** | `identity-center` |
| **Produces** | The metadata XML file that `aws_iam_saml_provider` (layer 04) registers, and the group-to-authorization-rule mapping the Client VPN endpoint enforces |
| **Teardown** | Removing it breaks Client VPN federation until a replacement is registered and the SAML provider's metadata is refreshed; not otherwise load-bearing for any other layer |

## Examples

- Gates layer 04 specifically: `aws_ec2_client_vpn_endpoint` cannot federate without the SAML provider, and the SAML provider cannot exist without this application's exported metadata.
- Client VPN authentication is two factors, not one: mutual TLS proves possession of a device certificate, this application's SSO proves which person — revoking access is revoking the group membership here plus the certificate's CRL, without touching IAM in any account.
- Authorization is by IdP group: a `network-ops` group reaches the management CIDR, a `dev` group reaches only the dev CIDR — enforced downstream by `aws_ec2_client_vpn_authorization_rule`, not by this resource itself.
