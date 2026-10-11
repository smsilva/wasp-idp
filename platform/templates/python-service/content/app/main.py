import os

from fastapi import FastAPI

APP_NAME = os.environ.get("APP_NAME", "python-service")

app = FastAPI(title=APP_NAME)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": APP_NAME, "message": "hello"}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
