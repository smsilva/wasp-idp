# aws_ec2_transit_gateway_route_table

|  |  |
|---|---|
| **Description** | A routing table attached to the transit gateway. One exists for the hub (`tgw-rt-hub`) and one per tenant spoke (`tgw-rt-<spoke>`) — the tenant table is what makes per-tenant isolation possible without relying on a security group. |
| **Provider** | `terraform · aws` (hub table: default provider, account `network`; spoke table: `aws.network` alias from the spoke's own state) |
| **Type** | `TGW route table` |
| **Layer** | `04 · connectivity` (hub table); recurs in `05 · control-plane` (the tenant table, `aws_ec2_transit_gateway_route_table.spoke`) |
| **State** | `connectivity` (hub table) / `control-plane` (tenant table) |
| **Dependencies** | `aws_ec2_transit_gateway.hub` (both tables reference the same transit gateway id, the spoke table via `data.aws_ec2_transit_gateway.hub`) |
| **Produces** | `id` — consumed by `aws_ec2_transit_gateway_route_table_association` and, for the tenant table, by both `aws_ec2_transit_gateway_route_table_propagation` resources |
| **Teardown** | Its associations and propagations must go first; the tenant table itself is destroyed along with the spoke's state, so no orphan is left on the hub side |

## Examples

- The tenant table's lifecycle follows the *spoke*, not the account that owns the transit gateway — it lives in the spoke's Terraform state via an `aws.network`-aliased provider, even though the resource itself belongs to the `network` account. This is the state-boundary-by-lifecycle rule applied literally.
- Only the hub table is created in `connectivity`; a spoke's tenant table does not exist until that spoke's `control-plane`-equivalent state applies its own attachment.
