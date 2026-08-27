# aws_s3_bucket_ownership_controls

|  |  |
|---|---|
| **Description** | Sets `object_ownership = BucketOwnerEnforced` on the state bucket, which disables ACLs entirely — every object is owned by the bucket account regardless of who wrote it. |
| **Provider** | `terraform · aws` |
| **Type** | `S3 ownership controls` |
| **Layer** | `01 · state-backend` |
| **State** | `state-backend` |
| **Dependencies** | `aws_s3_bucket.this` |
| **Produces** | Nothing consumed downstream |
| **Teardown** | Goes with the bucket; `Permanent (prevent_destroy)` on the parent |
