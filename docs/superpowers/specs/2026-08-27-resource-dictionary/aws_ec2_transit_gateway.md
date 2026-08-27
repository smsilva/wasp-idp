# aws_ec2_transit_gateway

|  |  |
|---|---|
| **Description** | The single crossroads that connects the hub VPC to every spoke VPC. Created with `default_route_table_association = "disable"` and `default_route_table_propagation = "disable"` — isolation is the default, and any reachability between attachments has to be stated explicitly via a route table association/propagation. |
| **Provider** | `terraform · aws` (account `network`) |
| **Type** | `Transit Gateway` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` |
| **Dependencies** | `None` (root of the connectivity layer) |
| **Produces** | `id`, `arn` — consumed by `aws_ec2_transit_gateway_route_table.hub`, `aws_ec2_transit_gateway_vpc_attachment.hub`, `aws_ram_resource_association.tgw`, `aws_route.hub_to_tgw`, and read back as a `data` source from the spoke's `control-plane` state |
| **Teardown** | Every attachment (hub's and every spoke's) must be gone first; the `connectivity/us-east-1/scripts/destroy` script refuses to proceed if it finds an attachment outside its own state |

## Examples

- `dns_support = "enable"` gives DNS resolution between attachments, but does not resolve VPC *names* — that is a separate, still-planned layer (`06 · private DNS`).
- Both default flags start `true` in the AWS API; leaving them on would make every attachment reachable from every other attachment with nobody having asked for it.
