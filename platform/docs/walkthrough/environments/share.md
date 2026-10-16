# Share an environment

Team members (`team-alpha`, from [Teams](../teams/create.md)) now see the environment in `environment list` and **receive the kubeconfig**:

```bash
platform environment share demo \
  --team team-alpha

platform environment list
```

``` { .text .output title="output" }
✓ demo shared with team-alpha
NAME          PROFILE    ACCOUNT  STATUS  EXPIRES  OWNER            SHARED
demo          shared     —        ready   52m      you@example.com  team-alpha
checkin-test  ephemeral  —        ready   48m      you@example.com  —
```
