# aws_s3_bucket_policy

|  |  |
|---|---|
| **Description** | Denies any `s3:*` action on the state bucket or its objects when the request did not use TLS (`aws:SecureTransport = false`). The only bucket policy in this layer. |
| **Provider** | `terraform · aws` |
| **Type** | `S3 bucket policy` |
| **Layer** | `01 · state-backend` |
| **State** | `state-backend` |
| **Dependencies** | `aws_s3_bucket.this`, `aws_s3_bucket_public_access_block.this` (explicit `depends_on`) |
| **Produces** | Nothing consumed downstream |
| **Teardown** | Goes with the bucket; `Permanent (prevent_destroy)` on the parent |

## Examples

- Must be applied after the public-access block, or AWS refuses it as a policy that looks public — hence the explicit `depends_on` in code rather than relying on implicit ordering.
- The ARNs in the policy document are built from `var.bucket_name`, not from `aws_s3_bucket.this.arn`: this keeps the policy known at plan time, which lets a test assert on it under `mock_provider`.
