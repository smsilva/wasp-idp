# aws_s3_bucket

|  |  |
|---|---|
| **Description** | The bucket that holds every layer's Terraform state, including its own. Self-hosted: it was originally created inside the `network-foundation` state, then adopted into its own `state-backend` root via `terraform import`. |
| **Provider** | `terraform · aws` |
| **Type** | `S3 bucket` |
| **Layer** | `01 · state-backend` |
| **State** | `state-backend` |
| **Dependencies** | `None` |
| **Produces** | `bucket_name`, `bucket_arn` — consumed as the `-backend-config=bucket=` of every other root |
| **Teardown** | `Permanent (prevent_destroy)` |

## Examples

- Guarded twice: `prevent_destroy = true` in the lifecycle block, and `force_destroy` left at its default `false` so AWS also refuses to delete a non-empty bucket — it never will be empty, since it holds its own state.
- Moved out of the `network-foundation` root specifically so that destroying one region's hub VPC state could never reach the bucket that maps everything else.
- Bucket name carries an organization-level discriminator and is real only in a gitignored `terraform.tfvars`; in this repo referred to as `tfstate-<organization-id>`.
