# organization-account-access-role

|  |  |
|---|---|
| **Description** | The IAM role AWS auto-creates in every member account of an Organization with feature set `ALL`, assumable from the management account. It is the bootstrap access path into a brand-new account before that account has its own Identity Center permission set — used both for administrative verification and for the scripts that act inside a member account (e.g. `create-log-archive-bucket`). |
| **Provider** | `console` / implicit (auto-created by AWS on `create-account`; used via `aws-cli` `sts assume-role`, typically wrapped in a named CLI profile) |
| **Type** | `IAM Role` |
| **Layer** | `00 · accounts` |
| **Dependencies** | `organization` (feature set `ALL`) · the target account (created by `create-account`, which lands it at Root before any move) |
| **State** | `—` |
| **Produces** | Temporary STS credentials scoped to the member account — the access `log-archive-bucket`'s creation script and the initial `move-account`/verification steps rely on |
| **Teardown** | Not deletable by normal means while the account remains a member; superseded in day-to-day use once `identity-center` assigns a permission set to the account, but kept as the break-glass path if that later fails |

## Examples

- `create-account` does not accept a destination OU — the account is created at Root and `move-account` is a second, separate call; moving Root→Root (a no-op mistake) returns `DuplicateAccountException`.
- Recommended pattern is a named CLI profile (`role_arn` + `source_profile`) rather than a one-off `sts assume-role`, so the SDK renews the session automatically instead of exported credentials going stale in the shell.
- Remains the documented path #1 in the break-glass emergency-access process — preferred over logging in as the member account's root user, which is path #2 and reserved for cases where the management account itself is unreachable.
