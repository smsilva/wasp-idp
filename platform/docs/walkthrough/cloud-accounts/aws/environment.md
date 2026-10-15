# An environment in the account

An environment that names a cloud account is provisioned in it, not as a local vcluster: one VPC (`10.0.0.0/16`, no cost) in the first region of the account, created through Crossplane by the `crossplane_aws` provider (ADR 0032). A cluster in it comes later.

**Once per platform:** install Crossplane. It needs the base credential, so `--aws-profile` now or on an earlier run; later runs remember it:

```bash
platform init \
  --target local \
  --with-crossplane
```

``` { .text .output title="output" }
…
deploying Crossplane …
installing the Crossplane provider for AWS EC2 (pulls its package, a few minutes the first time) …
deploying the cloud environment provider (crossplane_aws) …
✓ environments in cloud accounts provisioned through Crossplane (crossplane_aws provider)
```

**On the account side:** the role needs permission to manage VPCs, besides the trust policy. With the profile of whoever administers the account:

```bash
cat > /tmp/vpc-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["ec2:CreateVpc", "ec2:DeleteVpc", "ec2:ModifyVpcAttribute", "ec2:CreateTags", "ec2:DeleteTags", "ec2:Describe*"],
    "Resource": "*"
  }]
}
EOF

aws iam put-role-policy \
  --role-name platform \
  --policy-name platform-vpc \
  --policy-document file:///tmp/vpc-policy.json \
  --profile <account-admin>
```

The account must be `ready` and have a region, and it must be yours, shared with one of your teams, or you are in `platform-admins`:

```bash
platform environment create demo-cloud \
  --profile ephemeral \
  --cloud-account demo-aws \
  --expires 1h \
  --wait

platform environment get demo-cloud
```

``` { .text .output title="output" }
provisioning demo-cloud (profile: ephemeral, cloud account: demo-aws) …
  NoProviderForCapability
  Provisioning
✓ demo-cloud ready
demo-cloud: ready
  vpc vpc-0123456789abcdef0 in us-east-1, cloud account demo-aws
  in cloud account demo-aws

next:

  platform cloud account get demo-aws
```

- It takes about 30 s: Crossplane creates the VPC with the account's role, through a `ProviderConfig` named after the account. AWS tags it with `platform.wasp.silvios.me/environment=demo-cloud`.
- A role without the VPC permissions leaves it in `ProvisioningFailed`, with the AWS error in the message.
- It has no vcluster: `environment get --admin`, `environment credential` and `workload deploy|apply|remove|route` answer `409`.
- The account is fixed at creation: the CRD refuses a change, and access to the account is checked only then. An unshare stops new environments, never the ones already there.
- An account in use is not removed: `platform cloud account remove demo-aws` answers `409` with the environment names.

Remove it before the next step. The VPC goes first; the environment, once Crossplane confirms it is gone (about 15 s). `--expires` does the same when the deadline passes:

```bash
platform environment delete demo-cloud
```

``` { .text .output title="output" }
✓ demo-cloud deleting
```
