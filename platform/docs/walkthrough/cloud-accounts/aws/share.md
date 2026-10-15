# Share the account

An account is private to whoever registered it. Sharing it with a team lets its members **use** it, the same way an environment is shared (ADR 0026): you share only with teams you belong to, and `platform-admins` share with any team.

```bash
platform cloud account share demo-aws \
  --team team-alpha

platform cloud account get demo-aws
```

``` { .text .output title="output" }
✓ demo-aws shared with team-alpha
demo-aws: ready
  vendor     aws
  role       arn:aws:iam::<account>:role/platform
  account    <account>
  caller     arn:aws:sts::<account>:assumed-role/platform/platform-verify-demo-aws
  validated  2026-10-11T12:00:00Z
  owner      you@example.com
  shared     team-alpha
Trust policy of arn:aws:iam::<account>:role/platform:
[...]

next:

  platform environment create <environment> \
    --profile <profile> \
    --cloud-account demo-aws

  platform cloud account share demo-aws \
    --team <team>
```

- A member of `team-alpha` sees the account in `list` and `get`, **without the trust policy**: it carries the ExternalId, which stays with you and `platform-admins`.
- Only you and `platform-admins` verify, share, unshare and remove it.
- A team with an account shared with it is in use: `platform team delete team-alpha` answers `409` with `cloudaccount/demo-aws` until you unshare.

Stop sharing before the next step:

```bash
platform cloud account unshare demo-aws \
  --team team-alpha
```

``` { .text .output title="output" }
✓ demo-aws no longer shared with team-alpha
```
