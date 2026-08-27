# aws_ec2_client_vpn_network_association

|  |  |
|---|---|
| **Description** | Associates the Client VPN endpoint with a target subnet, moving it out of `pending-associate` and making it actually connectable. One per hub private subnet (one per AZ), via `for_each` over `data.aws_subnets.hub_private.ids`. |
| **Provider** | `terraform · aws` (account `network`) |
| **Type** | `Client VPN network association` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` |
| **Dependencies** | `aws_ec2_client_vpn_endpoint.hub`, `data.aws_subnets.hub_private` |
| **Produces** | Its existence is what `aws_ec2_client_vpn_route` depends on for the same subnet |
| **Teardown** | Slow: ~7–10 minutes per association, in both create and destroy directions — this is the single largest contributor to a `connectivity` layer teardown taking over 10 minutes total |

## Examples

- The target subnet is private, not public: target-network requirements only call for a `/27` with 20 free IPs and no overlap with the client CIDR, not a route to an internet gateway — that IGW requirement belongs to a different (mutual-auth) tutorial where the tunnel itself is the path to the internet.
- AWS adds the VPC's own local route to the subnet automatically on association — it coexists with the explicitly-written supernet route via longest-prefix-match, no conflict.
