# The versions of a component

`build list` reads the version index: only builds whose `app-spec.yaml` passed the check are there, newest first:

```bash
platform build create \
  --component hello-api \
  --branch feat/greetings \
  --version 1.0.0-rc.1 \
  --wait

platform build list \
  --component hello-api
```

``` { .text .output title="output" }
building from feat/greetings @ 86a7c08 …
✓ app-spec.yaml valid · db (postgres), dns, route
✓ image hello-api:1.0.0-rc.1 pushed to the registry
VERSION                  BRANCH          CREATED
1.0.0-rc.1               feat/greetings  2026-10-11T19:09:22Z
0.1.0-greetings.86a7c08  feat/greetings  2026-10-11T19:08:02Z
```

Underneath, a build is a `Build` and a version is a `Version` in the catalog group:

```bash
kubectl --context k3d-platform-local --namespace platform-system get builds,versions.catalog.platform.wasp.silvios.me
```

!!! note
    The index keeps the image digest of each version. A `Build` is removed 24 h after it ends; its version stays.
