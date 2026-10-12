# Base credential

**With the base credential only:** run `init` once with a profile from `~/.aws` (`init` remembers the credential on later runs). Use a **dedicated IAM user**, with permission only for `sts:AssumeRole` and `sts:GetCallerIdentity`; with SSO, `init` warns when the credential expires.

```bash
platform init \
  --target local \
  --aws-profile <platform-profile>
```

``` { .text .output title="output" }
…
deploying the cloud account provider (aws_account) …
✓ cloud accounts verified by the aws_account provider
```
