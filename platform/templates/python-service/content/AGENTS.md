# AGENTS.md

`${{ values.name }}` is a FastAPI service created by the platform from the `python-service` template.

- Code in `app/`, tests in `tests/`: run `pytest` before every commit.
- `app-spec.yaml` (Score) declares what the service needs from each environment: add resources there, never hardcode hosts or credentials.
- `catalog-info.yaml` is the catalog entry: keep `owner` and `description` current.
- CI (`.github/workflows/ci.yaml`) tests every push and publishes the image to GHCR from `main`.
