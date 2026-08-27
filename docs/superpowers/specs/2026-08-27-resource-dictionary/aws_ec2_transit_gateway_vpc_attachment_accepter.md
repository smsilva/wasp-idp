# aws_ec2_transit_gateway_vpc_attachment_accepter

|  |  |
|---|---|
| **Description** | The hub-side acceptance of the spoke's cross-account TGW attachment. The TGW's `auto_accept_shared_attachments` is `disable`, so RAM sharing alone only invites the account — the attachment sits in `pendingAcceptance` until the TGW owner (`network` account) explicitly accepts it. This is the second of the two gates a cross-account attachment needs. |
| **Provider** | `terraform · aws.network` (aliased, hub side) |
| **Type** | `TGW attachment accepter` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` (hub account, spoke lifecycle) |
| **Dependencies** | `aws_ec2_transit_gateway_vpc_attachment.this` (`transit_gateway_attachment_id`) |
| **Produces** | Nothing new consumed downstream directly, but its acceptance is a prerequisite `depends_on` for `aws_ec2_transit_gateway_route_table_association.spoke`, both `aws_ec2_transit_gateway_route_table_propagation.*`, and `aws_route.spoke_to_hub` |
| **Teardown** | Torn down alongside the attachment it accepts; nothing downstream can be torn down before it releases the association/propagation |

## Examples

- RAM sharing (layer 03/04) resolves the *share* invitation; this resource resolves the *attachment* invitation — two distinct mechanisms. Without it, association/propagation/route calls fail with `IncorrectState` / `InvalidTransitGatewayID.NotFound`, neither of which mentions pending acceptance.
- Both halves of the same attachment (`aws_ec2_transit_gateway_vpc_attachment.this` and this accepter) must repeat the same `transit_gateway_default_route_table_association/propagation = false` values, or they fight over the default on every apply.
- Created with an explicit `depends_on` chain into the association/propagation/route resources — the attachment ID alone does not guarantee ordering with acceptance.
