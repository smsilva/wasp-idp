# aws_ec2_transit_gateway_route_table_association

|  |  |
|---|---|
| **Description** | Declares which route table an attachment consults when sending traffic. Exists once for the hub's attachment (against `tgw-rt-hub`) and once for each spoke's attachment (against its own `tgw-rt-<spoke>`). |
| **Provider** | `terraform · aws` — hub association: default provider in `connectivity`; spoke association: `aws.network` alias in the spoke's own state (same lifecycle boundary as the tenant route table) |
| **Type** | `TGW route table association` |
| **Layer** | `04 · connectivity` (hub side); recurs in `05 · control-plane` (spoke side) |
| **State** | `connectivity` / `control-plane` |
| **Dependencies** | `aws_ec2_transit_gateway_vpc_attachment` (its own side) and `aws_ec2_transit_gateway_route_table` (its own side) |
| **Produces** | Nothing consumed further downstream — it is a pure binding |
| **Teardown** | Must go before the attachment and before the route table it references |

## Examples

- This is the resource that actually determines "sending" reachability — the attachment can exist without it, but traffic sent from that attachment has nowhere to look up a route until the association exists.
- Not to be confused with propagation (`aws_ec2_transit_gateway_route_table_propagation`, layer `05`), which controls whether *other* attachments learn routes *from* this one — association is about outbound lookup, propagation is about advertising inbound.
