# ${{ values.name }}

${{ values.description }}

FastAPI service created by the platform from the template `python-service`.

- `GET /`: the home page. It shows the build that answered (version, commit, pod), the PostgreSQL it connected to (green), the error when it could not (red) or that no database is configured (grey), and what this version does
- `GET /api/info`: name, title, version, commit and features, as JSON
- `GET /api/db`: the database check of the home page, as JSON; `503` when the database is unreachable
- `GET /healthz`: liveness and readiness; it never touches the database
- `GET /docs` and `GET /openapi.json`: the API docs (Swagger UI) and the OpenAPI document

What the page shows comes from three places:

- **Parameters** chosen when the component was created (`title`, `theme`): the `APP_TITLE` and `APP_THEME` variables of `app-spec.yaml`, which can differ per environment without a rebuild.
- **Code**: the list in `app/features.py`. Add an entry with each endpoint you add (`new=True` while it is the change being shipped) and it shows on the page after the deploy.
- **Build**: `APP_VERSION` and `APP_COMMIT`, baked into the image by `platform-build.yaml`.

CI tests every pull request and every push to `main`. `platform build create --component ${{ values.name }} --branch <branch>` runs `.github/workflows/platform-build.yaml`, which publishes `<registry>/${{ values.name }}:<version>` to the registry of the build (`platform registry list`): the version comes from the Conventional Commits since the last `v<version>` tag (Commitizen, `.cz.toml`), with the suffix `-<branch>.<sha7>` outside `main`. What the service needs from each environment is declared in `app-spec.yaml`.

Calls to other services go through `httpx`: `app/telemetry.py` passes each request's OpenTelemetry `baggage` and `traceparent` on to them, which keeps the platform's routing by baggage (`platform workload route --baggage`) along the whole chain of calls.

## Local run

Without `DATABASE_HOST` the page shows that no database is configured. With a local PostgreSQL, export `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`, `DATABASE_USER` and `DATABASE_PASSWORD` first; the database test (`tests/test_database.py`) also runs then, as it does in CI.

    python3 -m venv .venv && . .venv/bin/activate
    pip install --requirement requirements.txt --requirement requirements-dev.txt
    pytest
    uvicorn app.main:app --reload --port ${{ values.port }}
