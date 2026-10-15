# CRDs underneath

```bash
kubectl get domains.catalog.platform.wasp.silvios.me \
  --context k3d-platform-local \
  --namespace platform-system
```

``` { .text .output title="output" }
NAME       PARENT     OWNER
booking    tailwind   team-alpha
tailwind              team-alpha
```

!!! tip "The catalog belongs to the platform"
    It works with Backstage stopped.
