# aws_s3_bucket_server_side_encryption_configuration

|  |  |
|---|---|
| **Description** | SSE-S3 (`AES256`) encryption at rest for the state bucket. Every layer's Terraform state — including resource attributes that may be sensitive — is encrypted on disk in S3. |
| **Provider** | `terraform · aws` |
| **Type** | `S3 SSE configuration` |
| **Layer** | `01 · state-backend` |
| **State** | `state-backend` |
| **Dependencies** | `aws_s3_bucket.this` |
| **Produces** | Nothing consumed downstream |
| **Teardown** | Goes with the bucket; `Permanent (prevent_destroy)` on the parent |
