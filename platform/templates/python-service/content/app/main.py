import os

from fastapi import FastAPI

from app.telemetry import instrument

APP_NAME = os.environ.get("APP_NAME", "python-service")

app = FastAPI(title=APP_NAME)
instrument(app)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": APP_NAME, "message": "hello"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
