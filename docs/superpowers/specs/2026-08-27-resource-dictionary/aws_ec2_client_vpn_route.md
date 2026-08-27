# aws_ec2_client_vpn_route

|  |  |
|---|---|
| **Description** | Pushes one route — the entire supernet (`10.0.0.0/12`) — to the client, per associated subnet. Route is topology here (what exists and is reachable) and, deliberately, does not grow per spoke; what grows per spoke is the authorization rule (policy), not this route. |
| **Provider** | `terraform · aws` (account `network`) |
| **Type** | `Client VPN route` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` |
| **Dependencies** | `aws_ec2_client_vpn_endpoint.hub`, `data.aws_subnets.hub_private` (`for_each`), and an explicit `depends_on = [aws_ec2_client_vpn_network_association.hub]` |
| **Produces** | Nothing consumed further downstream — terminal in the graph |
| **Teardown** | No particular ordering constraint beyond preceding the endpoint and the network association it depends on |

## Examples

- The explicit `depends_on` on the network association is necessary because `for_each` alone does not order the two resources against each other — creating the route before its own subnet is associated fails with "subnet not associated", and nothing about `for_each` guarantees the association resource for the *same key* finishes first.
- Client CIDR (`100.64.0.0/22`) never gets a route on the spoke side, and does not need one here either — the Client VPN's own SNAT behaviour means return traffic targets the hub VPC's CIDR, already covered by the supernet route, not the client CIDR.
