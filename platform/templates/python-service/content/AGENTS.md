# AGENTS.md

`${{ values.name }}` is a FastAPI service created by the platform from the `python-service` template.

- Code in `app/`, tests in `tests/`: run `pytest` before every commit.
- `app-spec.yaml` (Score) declares what the service needs from each environment: add resources there, never hardcode hosts or credentials.
- `catalog-info.yaml` is the catalog entry: keep `owner` and `description` current.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `feat!:`): they decide the next version.
- CI (`.github/workflows/ci.yaml`) tests every pull request and every push to `main`. Images come from `.github/workflows/platform-build.yaml`, which the platform dispatches: keep its file name, inputs and the `platform-build` artifact, they are the build contract.
