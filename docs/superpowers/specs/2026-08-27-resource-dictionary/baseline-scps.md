# baseline-scps

|  |  |
|---|---|
| **Description** | Five Service Control Policies acting as a preventive ceiling on Root and each OU: deny leaving the Organization, protect the organization trail, restrict to approved regions, require IMDSv2, and deny the root user. An SCP does not grant anything — it restricts what even `AdministratorAccess` can do in an affected account. |
| **Provider** | `aws-cli (scripts/apply-baseline-service-control-policy)` |
| **Type** | `Service Control Policy ×5` |
| **Layer** | `00 · accounts` |
| **State** | `—` |
| **Dependencies** | `organization` (feature set `ALL`) · `ou-structure` (attachment targets) · the `SERVICE_CONTROL_POLICY` policy type enabled on Root (a separate, asynchronous one-off step) |
| **Produces** | `approved-regions` — every Terraform layer downstream fails at its first `Create*` if its region is not on this list |
| **Teardown** | Detach before deleting the target OU; `DenyLeaveOrganization` and `ProtectCloudTrail` on Root are meant to outlive every other layer |

## Examples

- `DenyOutsideApprovedRegions` is org-wide per apply: `apply-baseline-service-control-policy --regions us-east-1,us-west-2` rewrites it everywhere at once — there is no way to approve a region for one account only.
- The `NotAction` list must exempt inherently global services (IAM, Organizations, Route 53, CloudFront, Support), or the region-restriction policy blocks the very actions needed to administer the account.
- The script is idempotent (`update-policy` plus re-attaching only what is missing), so re-running it after an OU rename is the way to confirm nothing is orphaned.
