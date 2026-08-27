# log-archive-bucket

|  |  |
|---|---|
| **Description** | The S3 bucket that receives the organization trail's events, in its own dedicated account (`log-archive`, OU `Security`) so that no audited administrator — including one with `AdministratorAccess` elsewhere — can delete their own trail. |
| **Provider** | `aws-cli (scripts/create-log-archive-bucket)` |
| **Type** | `S3 bucket` |
| **Layer** | `00 · accounts` |
| **State** | `—` |
| **Dependencies** | The `log-archive` account exists and is reachable via `organization-account-access-role` |
| **Produces** | Bucket name/ARN — the destination `organization-trail` writes to |
| **Teardown** | `organization-trail` should stop pointing at it first; otherwise permanent by design (it is the audit trail of the bootstrap itself) |

## Examples

- Configuration applied: all four Block Public Access flags, versioning, SSE-S3 with bucket key, `BucketOwnerEnforced` (ACLs off), and a bucket policy scoped to `cloudtrail.amazonaws.com`.
- The bucket policy needs **two** `Resource` prefixes, not one: `AWSLogs/<management-account-id>/*` for the management account's own events and `AWSLogs/<organization-id>/*` for every member account's events. With only the second prefix the trail looks healthy but records nothing from the management account.
- Both policy statements condition on `aws:SourceArn` of the trail, which prevents a confused-deputy attack (another account pointing its own trail at this bucket) — but it also means renaming the trail invalidates the policy until the script is re-run.
- No lifecycle rule yet: retention (Standard → Glacier, expiration after N years) is an open compliance decision, not a technical one.
