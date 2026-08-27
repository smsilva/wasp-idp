# aws_ram_resource_association

|  |  |
|---|---|
| **Description** | Puts the transit gateway itself into the resource share, making it the concrete thing being shared rather than an empty share with nothing in it. |
| **Provider** | `terraform · aws` (account `network`) |
| **Type** | `RAM resource association` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` |
| **Dependencies** | `aws_ec2_transit_gateway.hub` (`resource_arn`), `aws_ram_resource_share.tgw` (`resource_share_arn`) |
| **Produces** | Nothing consumed further downstream — it is a pure binding |
| **Teardown** | Removing it (or the share) before every spoke's attachment is gone leaves those attachments without the sharing grant that let them exist cross-account |

## Examples

- Grows by exactly one entry total (the transit gateway), unlike `aws_ram_principal_association`, which grows by one per spoke account — this is "what is shared", that is "who it is shared with".
