# aws_ram_principal_association

|  |  |
|---|---|
| **Description** | Grants one spoke account id visibility of the shared transit gateway. One instance per entry in `var.spoke_account_ids` — this is what grows as new spoke accounts join, unlike the transit gateway route or the RAM resource association, which do not grow per spoke. |
| **Provider** | `terraform · aws` (account `network`) |
| **Type** | `RAM principal association` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` |
| **Dependencies** | `aws_ram_resource_share.tgw` (`resource_share_arn`); driven by `for_each = toset(var.spoke_account_ids)` |
| **Produces** | Nothing consumed further downstream directly, but its existence is a hard precondition for that account's `aws_ec2_transit_gateway_vpc_attachment` to succeed |
| **Teardown** | Removing an account's association before that account's attachment is destroyed leaves the attachment referencing a transit gateway it can no longer see |

## Examples

- With `aws_ram_sharing_with_organization` already enabled org-wide, an attachment created from a granted spoke account comes up already associated with the share — there is no `aws_ram_resource_share_accepter` on the spoke side to run.
