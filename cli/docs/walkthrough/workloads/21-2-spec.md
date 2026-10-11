# The spec of a version

When a build registers a version, it keeps the validated `app-spec.yaml` in the version index: deploying a version later reads the spec from the platform, not from GitHub. Build `feat/greetings` again, then read the spec of the newest version of the branch:

```bash
git -C /tmp/hello-api switch feat/greetings

platform build create \
  --component hello-api \
  --branch feat/greetings \
  --wait

platform workload spec get \
  --component hello-api \
  --branch feat/greetings
```

``` { .text .output title="output" }
building from feat/greetings @ 4f1d2e9 …
✓ app-spec.yaml valid · db (postgres), dns, route
✓ image hello-api:0.2.0-greetings.4f1d2e9 pushed to the registry
# hello-api 0.2.0-greetings.4f1d2e9 · feat/greetings @ 4f1d2e9
apiVersion: score.dev/v1b1
metadata:
  name: hello-api
resources:
  db:
    type: postgres
  dns:
    type: dns
  route:
    params:
      host: ${resources.dns.host}
      path: /
      port: 80
    type: route
containers:
  api:
    image: .
    variables:
      APP_NAME: hello-api
      DATABASE_HOST: ${resources.db.host}
      DATABASE_NAME: ${resources.db.name}
      DATABASE_PASSWORD: ${resources.db.password}
      DATABASE_USER: ${resources.db.username}
service:
  ports:
    http:
      port: 80
      targetPort: 8000
```

- The output is a valid `app-spec.yaml`: the first line is a YAML comment with the version, the branch and the commit.
- `--version <version>` picks one version; without `--version` or `--branch`, the newest version of the component.
- `--output json` adds the image, the digest and the creation time.

A version registered before the index kept the spec has none:

```bash
platform workload spec get \
  --component hello-api \
  --version 0.1.0-greetings.86a7c08
```

``` { .text .output title="output" }
✗ 409: SpecNotIndexed: hello-api 0.1.0-greetings.86a7c08 was indexed before the version index kept the spec: build it again under a new version
```

!!! note
    The spec is in `spec.appSpec` of the `Version`, in the catalog group: `kubectl --context k3d-platform-local --namespace platform-system get versions.catalog.platform.wasp.silvios.me hello-api.0.2.0-greetings.4f1d2e9 --output yaml`.
