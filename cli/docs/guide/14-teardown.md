# Teardown

```bash
platform environment list --output json | jq -r '.[].name' \
  | xargs --no-run-if-empty --max-args 1 platform environment delete
k3d cluster delete platform-local
rm ~/.config/platform/config.yaml
```

Apagar o `platform-local` leva junto os vclusters, que vivem dentro dele.
