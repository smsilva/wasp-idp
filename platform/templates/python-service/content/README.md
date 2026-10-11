# ${{ values.name }}

${{ values.description }}

FastAPI service created by the platform from the template `python-service`.

- `GET /` — app name and a greeting
- `GET /healthz` — liveness/readiness

Every push to `main` runs the tests and publishes `ghcr.io/wasp-foundry/${{ values.name }}:<sha>`. What the service needs from each environment is declared in `app-spec.yaml`.

## Local run

    python3 -m venv .venv && . .venv/bin/activate
    pip install --requirement requirements.txt --requirement requirements-dev.txt
    pytest
    uvicorn app.main:app --reload --port ${{ values.port }}
