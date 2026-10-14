# Tear down

```bash
platform environment list --output json \
  | jq -r '.[].name' \
  | xargs --no-run-if-empty --max-args 1 platform environment delete

k3d cluster delete platform-local

rm ~/.config/platform/config.yaml

make cli-uninstall
```

Deleting `platform-local` takes the vclusters with it, since they live inside it. Keycloak users, the Google credentials and the AWS base credential go with the cluster too: the next `init` needs them again.
