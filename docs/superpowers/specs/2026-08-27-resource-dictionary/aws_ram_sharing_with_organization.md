# aws_ram_sharing_with_organization

|  |  |
|---|---|
| **Description** | Org-wide toggle that enables AWS Resource Access Manager to share resources with principals across the whole Organization. It has no arguments beyond the computed `id` — its existence is the "on" state, there is no `enabled = true` to declare. First of the two gates any cross-account Transit Gateway attachment needs. |
| **Provider** | `terraform · aws.management` (aliased) |
| **Type** | `RAM organization sharing` |
| **Layer** | `03 · dns` |
| **State** | `dns` |
| **Dependencies** | `None` — must run under the management account, where the Organization itself lives |
| **Produces** | The organization-wide capability to `AssociateResourceShare` with principals from other accounts in the same Organization; consumed implicitly by `aws_ram_principal_association` in layer 04 |
| **Teardown** | Permanent — not torn down with the nightly `connectivity` destroy; disabling and re-enabling it daily for a resource it does not own would be backwards |

## Examples

- Lives in the `dns` state (T0, permanent), not in `connectivity` (T1, destroyed nightly) — it is Organization-wide configuration, not part of the Transit Gateway's lifecycle.
- Confirmed on the first real apply: without it, RAM refuses `AssociateResourceShare` with an `OperationNotPermittedException` until this toggle is on, org-wide.
- The second gate is the explicit `aws_ec2_transit_gateway_vpc_attachment_accepter` on the hub side (layer 05) — RAM sharing alone does not auto-accept the attachment itself.
