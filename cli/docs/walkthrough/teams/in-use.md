# A team in use

**A team in use is not deleted:** the catalog imported [from Backstage](../catalog/plan.md) has entities owned by `team-alpha`.

```bash
platform team delete team-alpha
```

``` { .text .output title="output" }
✗ 409: team 'team-alpha' is still in use: domain/communication, …; unshare or change the owner first
```
