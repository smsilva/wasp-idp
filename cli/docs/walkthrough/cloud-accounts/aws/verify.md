# Verify

```bash
platform cloud account verify demo-aws \
  --wait

platform cloud account list
```

``` { .text .output title="output" }
✓ demo-aws ready (account <account>)
NAME      VENDOR  ACCOUNT    STATUS  VALIDATED             OWNER            SHARED
demo-aws  aws     <account>  ready   2026-10-11T12:00:00Z  you@example.com  —
```
