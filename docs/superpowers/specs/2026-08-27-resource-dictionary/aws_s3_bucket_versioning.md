# aws_s3_bucket_versioning

|  |  |
|---|---|
| **Description** | Enables version history on the state bucket. It is the recovery path after a corrupted or concurrent apply overwrites a state file. |
| **Provider** | `terraform · aws` |
| **Type** | `S3 versioning configuration` |
| **Layer** | `01 · state-backend` |
| **State** | `state-backend` |
| **Dependencies** | `aws_s3_bucket.this` |
| **Produces** | Nothing consumed downstream — an operational safety net, not a data dependency |
| **Teardown** | Goes with the bucket; `Permanent (prevent_destroy)` on the parent |

## Examples

- Not optional on a state bucket: without it, a bad apply or a lock race silently destroys the only record of what exists in AWS, with no way back.
