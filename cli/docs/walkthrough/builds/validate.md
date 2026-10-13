# Validate a spec before the build

The Workload Spec is the `app-spec.yaml` (Score) of a version. `workload spec validate` runs the same check as the build ([What a build refuses](refused.md)) on a local file, before any commit: the Score schema, the resource types the platform provisions and each `resources.<name>.id` in the catalog. Anyone signed in can run it.

In the clone of [Build a branch](create.md), on `feat/greetings`:

```bash
cd /tmp/hello-api

platform workload spec validate
```

``` { .text .output title="output" }
✓ app-spec.yaml valid · db (postgres), dns, route
```

On `feat/bad-spec` ([What a build refuses](refused.md)), the same errors the build reported come back without a build:

```bash
git -C /tmp/hello-api switch feat/bad-spec

platform workload spec validate \
  --file /tmp/hello-api/app-spec.yaml
```

``` { .text .output title="output" }
  resources.db.id: resource 'orders-db' is not in the catalog
  resources.cache.type: 'redis' is not a resource type of the platform (postgres, dns, route)
✗ app-spec.yaml: 2 error(s)
```

- `--file` defaults to `app-spec.yaml` in the current directory.
- An invalid spec exits with code `1`, also with `--output json`: use it in a pre-commit hook or a CI step.
