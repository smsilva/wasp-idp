# CRDs underneath

```bash
kubectl get domains.catalog.platform.wasp.silvios.me \
  --context k3d-platform-local \
  --namespace platform-system
```

``` { .text .output title="output" }
NAME            PARENT          OWNER
communication                   team-alpha
messaging       communication   team-alpha
```

!!! tip "The catalog belongs to the platform"
    It works with Backstage stopped.
