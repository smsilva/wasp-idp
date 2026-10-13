# ExternalId and removal

Remove the `sts:ExternalId` condition from the policy and run `verify --wait` again: the account moves to `ExternalIdNotEnforced`, because without the condition anyone who knows the role and trusts the same base credential could register it. Restore the original policy and remove the account:

```bash
platform cloud account remove demo-aws
```

``` { .text .output title="output" }
✓ cloud account demo-aws removed
```
