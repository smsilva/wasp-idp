# organization

|  |  |
|---|---|
| **Description** | The AWS Organization itself, created with feature set `ALL`. Without `ALL`, Service Control Policies do not work at all — `CONSOLIDATED_BILLING` mode (the legacy default) blocks most of the security guardrails this reference depends on. It is the container every OU, account, and SCP in this layer hangs off. |
| **Provider** | `aws-cli` (`aws organizations create-organization --feature-set ALL`) |
| **Type** | `AWS Organizations organization` |
| **Layer** | `00 · accounts` |
| **State** | `—` |
| **Dependencies** | None — created from the one account you already have, which becomes the management account |
| **Produces** | `organization-id` (`o-xxxxxxxxxx`), the management account's designation, the ability to enable `SERVICE_CONTROL_POLICY` as a policy type |
| **Teardown** | Permanent for the life of this reference — closing an Organization requires closing or removing every member account first |

## Examples

- If the Organization already exists in `CONSOLIDATED_BILLING` mode, `enable-all-features` upgrades it, but every existing member account must accept the change first.
- The Organization ID (`o-xxxxxxxxxx`) is a distinct namespace from any account ID — the organization trail's bucket policy needs both (see `organization-trail.md`).
