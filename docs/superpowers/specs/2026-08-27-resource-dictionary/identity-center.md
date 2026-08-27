# identity-center

|  |  |
|---|---|
| **Description** | IAM Identity Center (formerly AWS SSO), enabled once on the management account. Federates a single human identity and grants access per account through reusable permission sets, assigned to groups rather than individual users so the assignment survives team turnover. |
| **Provider** | `aws-cli (scripts/assign-permission-set, scripts/show-permission-sets, scripts/revoke-permission-set)` + console (initial instance enablement) |
| **Type** | `IAM Identity Center instance + permission sets` |
| **Layer** | `00 · accounts` |
| **State** | `—` |
| **Dependencies** | `organization` · the target account must exist (`organization-account-access-role` is the bootstrap path into it before its own permission set is assigned) |
| **Produces** | Per-account, per-group assignments — the credential path `aws sso login` uses, and what `saml-application` builds on top of for Client VPN federation |
| **Teardown** | Revoking an assignment (`revoke-permission-set`) leaves the permission set intact for other accounts; the instance itself is not expected to be torn down |

## Examples

- Assigning to `--group`, not `--user`, is deliberate: a person leaving the team does not require touching every account's assignment.
- There is no "update assignment" API — swapping a permission set is two calls: assign the new one, then revoke the old. Assigning first avoids a window with no access.
- A newly created member account is not in the SSO portal until `assign-permission-set` runs against it; until then, `organization-account-access-role` is the only way in.
- The `log-archive` account is deliberately assigned `ReadOnlyAccess`, not `AdministratorAccess` — its value comes from nobody being able to delete what is stored there.
