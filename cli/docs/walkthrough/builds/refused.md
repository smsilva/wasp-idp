# What a build refuses

A version whose `app-spec.yaml` is not valid does not exist for the platform. On a branch that declares a resource type the platform does not provision, and a shared resource that is not in the catalog:

```bash
git -C /tmp/hello-api switch --create feat/bad-spec main

sed --in-place \
  --expression '/^    type: postgres$/a\    id: orders-db' \
  --expression '/^    type: postgres$/a\  cache:' \
  --expression '/^    type: postgres$/a\    type: redis' \
  /tmp/hello-api/app-spec.yaml

git -C /tmp/hello-api commit \
  --all \
  --message "feat: cache and shared database"

git -C /tmp/hello-api push --set-upstream origin feat/bad-spec

platform build create \
  --component hello-api \
  --branch feat/bad-spec \
  --wait
```

``` { .text .output title="output" }
building from feat/bad-spec @ 9590d3e …
  resources.db.id: resource 'orders-db' is not in the catalog
  resources.cache.type: 'redis' is not a resource type of the platform (postgres, dns, route)
  run: https://github.com/wasp-foundry/hello-api/actions/runs/38166818390
✗ hello-api-8757ff: InvalidSpec: app-spec.yaml at 9590d3e: 2 error(s)
```

The image is in the registry, but `build list` does not show the version. `build get` keeps the steps for 24 h:

```bash
platform build get hello-api-8757ff
```

``` { .text .output title="output" }
build/hello-api-8757ff (InvalidSpec)
  component     hello-api
  branch        feat/bad-spec
  version       0.1.0-bad-spec.9590d3e
  registry      ghcr-wasp-foundry (ghcr.io/wasp-foundry/hello-api)
  commit        9590d3e
  run           https://github.com/wasp-foundry/hello-api/actions/runs/38166818390
  ✓ Dispatched    platform-build.yaml dispatched on feat/bad-spec
  ✓ Running       https://github.com/wasp-foundry/hello-api/actions/runs/38166818390
  ✓ Succeeded     image ghcr.io/wasp-foundry/hello-api:0.1.0-bad-spec.9590d3e pushed
  ✗ SpecValidated app-spec.yaml at 9590d3e: 2 error(s)
      resources.db.id: resource 'orders-db' is not in the catalog
      resources.cache.type: 'redis' is not a resource type of the platform (postgres, dns, route)
```

Before GitHub, the API refuses a version already in the index, since the CI would push its tag again:

```bash
platform build create \
  --component hello-api \
  --branch main \
  --version 1.0.0-rc.1
```

``` { .text .output title="output" }
✗ 409: build of 'hello-api': version 1.0.0-rc.1 is already in the index (commit 86a7c08)
```

A repo without the workflow on its default branch (created before the template had it, for example) stops at `WorkflowNotFound`; adding `platform-build.yaml` by pull request fixes it:

``` { .text .output title="output" }
✗ greeting-api-71fbc9: WorkflowNotFound: wasp-foundry/greeting-api has no .github/workflows/platform-build.yaml on its default branch: the build contract asks for it (workflow_dispatch with request-id and version)
```
