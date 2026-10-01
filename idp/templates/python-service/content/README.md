# ${{ values.name }}

${{ values.description }}

FastAPI service created from the wasp-idp Backstage template `python-service`.

- `GET /` — app name and a greeting
- `GET /healthz` — liveness/readiness

Every push to `main` runs the tests, publishes `ghcr.io/wasp-foundry/${{ values.name }}:<sha>` and bumps the tag in [`wasp-foundry/gitops`](https://github.com/wasp-foundry/gitops/tree/main/apps/${{ values.name }}), which ArgoCD deploys.

## Local run

    python3 -m venv .venv && . .venv/bin/activate
    pip install --requirement requirements.txt --requirement requirements-dev.txt
    pytest
    uvicorn app.main:app --reload
