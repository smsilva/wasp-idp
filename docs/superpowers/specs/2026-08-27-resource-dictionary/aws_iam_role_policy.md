# aws_iam_role_policy

|  |  |
|---|---|
| **Description** | Inline (non-managed) policy grants on a Pod Identity role, for permissions with no suitable AWS-managed policy: Secrets Manager reads (`secretsmanager:GetSecretValue`, `secretsmanager:DescribeSecret`) for External Secrets, and `sts:AssumeRole` + `sts:TagSession` into every target account's `crossplane-*` roles for Crossplane. |
| **Provider** | `terraform · aws` |
| **Type** | `IAM inline policy` |
| **Layer** | `05 · control-plane` |
| **State** | `control-plane` |
| **Dependencies** | The `aws_iam_role.this` it is inline on (created only when the Pod Identity module instance is given a `policy_json`; `count = var.policy_json == null ? 0 : 1`) |
| **Produces** | Nothing consumed downstream directly — its effect is the permission the role's Pod Identity association grants at runtime |
| **Teardown** | Removed with its role, before the role itself can be deleted |

## Examples

- The Crossplane inline policy's `Resource` is built from `var.target_account_ids` — one `arn:aws:iam::<account-id>:role/crossplane-*` per target account, so the Crossplane pod can assume into every spoke it is meant to manage and nowhere else.
- The EBS CSI Pod Identity module instance has no inline policy (`policy_json = null`) — it relies entirely on the managed `AmazonEBSCSIDriverPolicy` attachment instead.
