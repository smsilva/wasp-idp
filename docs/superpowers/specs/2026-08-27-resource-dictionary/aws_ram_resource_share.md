# aws_ram_resource_share

|  |  |
|---|---|
| **Description** | The RAM share through which spoke accounts are granted visibility of the hub's transit gateway. `allow_external_principals = false` — the share stays inside the Organization; every spoke account is already a member of it. |
| **Provider** | `terraform · aws` (account `network`) |
| **Type** | `RAM resource share` |
| **Layer** | `04 · connectivity` |
| **State** | `connectivity` |
| **Dependencies** | `None` directly; created alongside `aws_ec2_transit_gateway.hub` but does not reference it |
| **Produces** | `arn` — consumed by `aws_ram_resource_association.tgw` and `aws_ram_principal_association.spoke` |
| **Teardown** | Its associations (resource and principal) should be removed with or before it; removing the share revokes every spoke's visibility of the transit gateway at once |

## Examples

- Existing without `aws_ram_sharing_with_organization` enabled at the Organization level does nothing: the very first apply against a fresh Organization got `OperationNotPermittedException` on `AssociateResourceShare` until that org-wide toggle was turned on (a one-off, permanent resource that lives in `dns`, not here).
- RAM here only resolves the *sharing* invitation; it does not resolve *acceptance* of an individual attachment — that is `aws_ec2_transit_gateway_vpc_attachment_accepter`, a separate mechanism, needed because the transit gateway sets `auto_accept_shared_attachments = "disable"`.
