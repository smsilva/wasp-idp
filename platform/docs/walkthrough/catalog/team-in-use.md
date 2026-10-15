# A team in use

**A team in use is not deleted:** the catalog imported [from Backstage](plan.md) has entities owned by `team-airport`.

```bash
platform team delete team-airport
```

``` { .text .output title="output" }
✗ 409: team 'team-airport' is still in use: domain/airport, system/bag-tracking, system/boarding-pass, system/seat-map; unshare or change the owner first
```
