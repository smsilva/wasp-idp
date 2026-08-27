# organization-trail

|  |  |
|---|---|
| **Description** | A multi-region CloudTrail trail created in the management account with `--is-organization-trail`, capturing events from every member account — including ones created later, with no onboarding step. Created before any OU or project account so the bootstrap itself is not the one unaudited window. |
| **Provider** | `aws-cli (scripts/create-organization-trail)` |
| **Type** | `CloudTrail trail` |
| **Layer** | `00 · accounts` |
| **State** | `—` |
| **Dependencies** | `organization` · `log-archive-bucket` (destination) · trusted access for `cloudtrail.amazonaws.com` enabled via `organization-account-access-role`-style service access |
| **Produces** | The org-wide audit record every later layer's bootstrap (IAM users, roles, cross-account access) is provable against |
| **Teardown** | `ProtectCloudTrail` (in `baseline-scps`) denies disabling it from any member account; intended to be permanent |

## Examples

- `create-trail` does not start logging by itself — `start-logging` is a separate call, and a stopped trail looks identical to a healthy one in `describe-trails` (only `get-trail-status` shows state). The script always reasserts `start-logging`.
- `--enable-log-file-validation` publishes signed digest files, proving after the fact that no log was altered or deleted — a policy-immutable bucket is not the same as a verifiable one.
- Cost at this Organization's scale is under US$ 1/month: the first copy of management events per account is free; what grows the bill is data events (S3 object-level, Lambda invoke) or a second trail, neither of which is enabled here.
