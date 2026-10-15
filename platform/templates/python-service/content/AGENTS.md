# AGENTS.md

`${{ values.name }}` is a FastAPI service created by the platform from the `python-service` template.

- Code in `app/`, tests in `tests/`: run `pytest` before every commit.
- The home page is `app/templates/index.html` (Jinja2, rendered by FastAPI): what this version does comes from `app/features.py`, so add an entry there with every endpoint you add, `new=True` while it is the change being shipped. Give new routes a `tags`, a `summary` and typed responses: `/docs` (Swagger UI) is how people try them.
- `app/database.py` checks the database on every page load and on `GET /api/db`; `/healthz` never touches it, so a database outage does not restart the pod. Never put the password in a response or a log, and keep `SHOW_DATABASE_DETAILS` `"false"` outside demos: it shows the host, user and errors to anyone.
- `app-spec.yaml` (Score) declares what the service needs from each environment: add resources there, never hardcode hosts or credentials.
- Call other services with `httpx`, from inside the request that needs them: `app/telemetry.py` passes the request's `baggage` and `traceparent` on to every call. The platform routes a sandbox by baggage (`sandbox=pr-42`), and one service that drops it sends every call after it to the stable versions. Never build those headers by hand, and keep the request's context when work moves to another thread or task.
- `catalog-info.yaml` is the catalog entry: keep `owner` and `description` current.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `feat!:`): they decide the next version.
- CI (`.github/workflows/ci.yaml`) tests every pull request and every push to `main`. Images come from `.github/workflows/platform-build.yaml`, which the platform dispatches: keep its file name, inputs and the `platform-build` artifact, they are the build contract.
