# aws_s3_bucket_public_access_block

|  |  |
|---|---|
| **Description** | All four public-access blocks (`block_public_acls`, `block_public_policy`, `ignore_public_acls`, `restrict_public_buckets`) enabled on the state bucket. Must exist before the bucket policy is applied. |
| **Provider** | `terraform · aws` |
| **Type** | `S3 public access block` |
| **Layer** | `01 · state-backend` |
| **State** | `state-backend` |
| **Dependencies** | `aws_s3_bucket.this` |
| **Produces** | Nothing consumed downstream, but gates `aws_s3_bucket_policy.this` |
| **Teardown** | Goes with the bucket; `Permanent (prevent_destroy)` on the parent |

## Examples

- `aws_s3_bucket_policy.this` sets an explicit `depends_on` this resource: applying the deny-insecure-transport policy before the block is in place makes AWS reject the policy as looking public.
