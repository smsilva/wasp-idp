import os
import socket
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import database
from app.features import FEATURES, Feature
from app.telemetry import instrument

APP_NAME = os.environ.get("APP_NAME", "python-service")
APP_TITLE = os.environ.get("APP_TITLE") or APP_NAME
APP_DESCRIPTION = os.environ.get("APP_DESCRIPTION", "")
THEMES = ("indigo", "teal", "amber", "rose")
APP_THEME = os.environ.get("APP_THEME") if os.environ.get("APP_THEME") in THEMES else THEMES[0]
# Baked into the image by platform-build.yaml (Dockerfile ARGs); a local run has neither.
APP_VERSION = os.environ.get("APP_VERSION", "dev")
APP_COMMIT = os.environ.get("APP_COMMIT", "unknown")

app = FastAPI(title=APP_TITLE, version=APP_VERSION, description=APP_DESCRIPTION or f"{APP_NAME}, made from the python-service template.")
instrument(app)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


class Info(BaseModel):
    app: str
    title: str
    description: str
    version: str
    commit: str
    pod: str
    features: list[Feature]


def info() -> Info:
    return Info(app=APP_NAME, title=APP_TITLE, description=APP_DESCRIPTION, version=APP_VERSION, commit=APP_COMMIT, pod=socket.gethostname(), features=FEATURES)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"info": info(), "theme": APP_THEME, "db": database.check()})


@app.get("/api/info", tags=["about"], summary="Name, version and commit of this build")
def api_info() -> Info:
    return info()


@app.get(
    "/api/db",
    tags=["about"],
    summary="Check the connection to the database",
    response_model_by_alias=True,
    responses={503: {"model": database.DatabaseStatus, "description": "The database is unreachable"}},
)
def api_db(response: Response) -> database.DatabaseStatus:
    status = database.check()
    if status.status == "failed":
        response.status_code = 503
    return status


@app.get("/healthz", tags=["about"], summary="Liveness and readiness; never touches the database")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
