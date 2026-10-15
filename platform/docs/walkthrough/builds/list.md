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
building from feat/greetings @ b5f9569 …
✓ app-spec.yaml valid · db (postgres), dns, route
✓ image hello-api:1.0.0-rc.1 pushed to ghcr-wasp-foundry (ghcr.io/wasp-foundry/hello-api)
NAME                               VERSION                  BRANCH          REGISTRY           CREATED
hello-api.1.0.0-rc.1               1.0.0-rc.1               feat/greetings  ghcr-wasp-foundry  2026-10-12T19:12:49Z
hello-api.0.1.0-greetings.b5f9569  0.1.0-greetings.b5f9569  feat/greetings  ghcr-wasp-foundry  2026-10-12T18:37:33Z
```

`platform catalog component get hello-api` shows the newest of both on its `builds` and `versions` lines, and the 5 newest with `--verbose` ([Components](../../reference/catalog.md#components)).

`NAME` is the version itself, and `build get` takes it too: it shows the build that produced the version, while that build lasts.

```bash
platform build get hello-api.1.0.0-rc.1
```

Underneath, a build is a `Build` and a version is a `Version` in the catalog group:

```bash
kubectl --context k3d-platform-local --namespace platform-system get builds,versions.catalog.platform.wasp.silvios.me
```

!!! note
    The index keeps the image digest of each version. A `Build` is removed 24 h after it ends; its version stays, and `build get <version>` then says the build is gone. A version written without a build (by `kubectl`, for instance) says so too.
