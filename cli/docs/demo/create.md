# Create the app

One command creates the repo from the golden path, pushes the first commit and registers the app in the catalog:

```bash
platform catalog component create hello-api \
  --system greeter \
  --wait
```

``` { .text .output title="output" }
  ✓ Validated: scm connection 'wasp-foundry' is ready
  ✓ Rendered: 19 files from python-service@5adb796c62a44bb2b580dda4ef7d21d49ae82ba9
  ✓ RepoCreated: wasp-foundry/hello-api created (public)
  ✓ Pushed: first commit c11d7df on main
  ✓ Protected: main changes only by pull request (no approval required)
  ✓ Registered: in the catalog (lifecycle: experimental)
✓ golden path “python-service” (default for service): repo wasp-foundry/hello-api created
✓ registered in the catalog (lifecycle: experimental)
✓ app-spec.yaml generated: container, postgres, route /
```

- **Golden path:** `python-service` is the default template for a `service`. It brings the code, the CI workflow and the `app-spec.yaml` (the app's Score: a container, a Postgres and a route).
- **Catalog:** `platform catalog component get hello-api` shows it under `greeter`, owned by `team-alpha`.
- **Repo:** `https://github.com/wasp-foundry/hello-api`, with `main` protected.
