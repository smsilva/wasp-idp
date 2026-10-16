# Create the app

One command creates the repo from the golden path, pushes the first commit and registers the app in the catalog:

```bash
platform catalog component create seat-selection \
  --system seat-map \
  --owner team-airport \
  --template python-service-with-postgresql-for-demo-only \
  --wait
```

- **Golden path:** `python-service` with the database details on its home page. It brings the code, the CI workflow and the `app-spec.yaml` (a container, a Postgres and a route). `--param theme=teal` changes its color; `--template node-service` runs the same journey on Node.js.
- **Catalog:** under `seat-map`, owned by `team-airport`.
- **Repo:** `wasp-foundry/seat-selection`, with `main` protected.
