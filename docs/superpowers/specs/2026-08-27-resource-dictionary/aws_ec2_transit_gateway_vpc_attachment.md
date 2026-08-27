# aws_ec2_transit_gateway_vpc_attachment

|  |  |
|---|---|
| **Description** | Plugs one VPC into the transit gateway. Two instances exist: the hub's own attachment (`connectivity`) and each spoke's attachment (its own state, e.g. `control-plane`). Without the hub's attachment, traffic arriving over the Client VPN tunnel in a hub private subnet has no way out to the transit gateway. |
| **Provider** | `terraform · aws` — the hub attachment uses the default provider in `connectivity` (account `network`); a spoke's attachment uses the spoke's own default provider (its own account owns the VPC), not `aws.network` |
| **Type** | `TGW VPC attachment` |
| **Layer** | `04 · connectivity` (hub side); recurs in `05 · control-plane` (spoke side) |
| **State** | `connectivity` / `control-plane` |
| **Dependencies** | `aws_ec2_transit_gateway.hub` (or `data.aws_ec2_transit_gateway.hub` on the spoke side), the VPC and its private subnets (`data.aws_vpc.hub`/`data.aws_subnets.hub_private` or `module.network`) |
| **Produces** | `id` — consumed by `aws_ec2_transit_gateway_route_table_association`, and on the spoke side additionally by `aws_ec2_transit_gateway_vpc_attachment_accepter` |
| **Teardown** | Must go before the transit gateway and before the owning VPC; a cross-account attachment stuck in `pendingAcceptance` or without a route pointing at it can block the associated route table's deletion |

## Examples

- `transit_gateway_default_route_table_association = false` and `..._propagation = false` are set explicitly on every attachment, mirroring the transit gateway's own default-disabled posture.
- A cross-account attachment (spoke side) needs `ignore_changes` on both `transit_gateway_default_route_table_association` and `transit_gateway_default_route_table_propagation` — these are write-only in the API and derived by inspecting route tables that live in the *other* account, so the provider's own account can never see them and the plan proposes `true -> false` forever without it.
- `transit_gateway_configuration` on the Client VPN endpoint is deliberately not used to attach the hub VPC — that path's implicit attachment takes "several hours" to delete per the provider's own warning and blocks deleting the transit gateway; associating a subnet directly is the path taken instead.
