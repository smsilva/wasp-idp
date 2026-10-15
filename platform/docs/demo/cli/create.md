# Create the app

One command creates the repo from the golden path, pushes the first commit and registers the app in the catalog:

```bash
platform catalog component create hello-api \
  --system greeter \
  --wait
```

- **Golden path:** `python-service` is the default template for a `service`. It brings the code, the CI workflow and the `app-spec.yaml` (the app's Score: a container, a Postgres and a route), and a home page that shows the version answering and the Postgres it connected to. `--param title=...` and `--param theme=teal` (`indigo`, `teal`, `amber`, `rose`) change its headline and color.
- **Catalog:** `platform catalog component get hello-api` shows it under `greeter`, owned by `team-alpha`.
- **Repo:** `https://github.com/wasp-foundry/hello-api`, with `main` protected.
