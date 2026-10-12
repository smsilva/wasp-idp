# ${{ values.name }}

${{ values.description }}

FastAPI service created by the platform from the template `python-service`.

- `GET /` — app name and a greeting
- `GET /healthz` — liveness/readiness

CI tests every pull request and every push to `main`. `platform build create --component ${{ values.name }} --branch <branch>` runs `.github/workflows/platform-build.yaml`, which publishes `ghcr.io/wasp-foundry/${{ values.name }}:<version>`: the version comes from the Conventional Commits since the last `v<version>` tag (Commitizen, `.cz.toml`), with the suffix `-<branch>.<sha7>` outside `main`. What the service needs from each environment is declared in `app-spec.yaml`.

Calls to other services go through `httpx`: `app/telemetry.py` passes each request's OpenTelemetry `baggage` and `traceparent` on to them, which keeps the platform's routing by baggage (`platform workload route --baggage`) along the whole chain of calls.

## Local run

    python3 -m venv .venv && . .venv/bin/activate
    pip install --requirement requirements.txt --requirement requirements-dev.txt
    pytest
    uvicorn app.main:app --reload --port ${{ values.port }}
