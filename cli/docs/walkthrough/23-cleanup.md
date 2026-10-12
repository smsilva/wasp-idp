# Cleanup

```bash
platform environment delete demo

platform environment delete greetings-test

kubectl --context k3d-platform-local get namespaces \
  | grep env- \
  || echo "no environments"

platform logout

platform whoami
```

``` { .text .output title="output" }
✓ Logged out
✗ not logged in: run 'platform login'
```

!!! tip
    `platform-local` stays up for the next round; to tear everything down, go back to [step 0](setup/00-from-scratch.md).
