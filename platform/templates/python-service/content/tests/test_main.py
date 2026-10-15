import importlib

import pytest
from fastapi.testclient import TestClient

import app.main


@pytest.fixture
def client(monkeypatch):
    """The app as a fresh import reads it from the environment, without a database."""
    monkeypatch.delenv("DATABASE_HOST", raising=False)

    def make(**environment):
        for key in ("APP_NAME", "APP_TITLE", "APP_DESCRIPTION", "APP_THEME", "APP_VERSION", "APP_COMMIT"):
            monkeypatch.delenv(key, raising=False)
        for key, value in environment.items():
            monkeypatch.setenv(key, value)
        return TestClient(importlib.reload(app.main).app)

    return make


def test_healthz_returns_ok(client):
    response = client().get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_info_reads_the_environment(client):
    body = client(APP_NAME="hello-alpha", APP_TITLE="Hello Alpha", APP_VERSION="0.2.0", APP_COMMIT="b5f9569abc").get("/api/info").json()
    assert body["app"] == "hello-alpha"
    assert body["title"] == "Hello Alpha"
    assert (body["version"], body["commit"]) == ("0.2.0", "b5f9569abc")
    assert [feature["endpoint"] for feature in body["features"]][:2] == ["GET /api/info", "GET /api/db"]


def test_info_falls_back_to_defaults(client):
    body = client().get("/api/info").json()
    assert (body["app"], body["title"], body["version"], body["commit"]) == ("python-service", "python-service", "dev", "unknown")


def test_home_page_shows_title_theme_version_and_features(client):
    response = client(APP_NAME="hello-alpha", APP_TITLE="Hello Alpha", APP_THEME="teal", APP_VERSION="0.2.0-greetings.b5f9569").get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = response.text
    assert "<h1>Hello Alpha</h1>" in page
    assert 'data-theme="teal"' in page
    assert "0.2.0-greetings.b5f9569" in page
    assert "Checks its database" in page
    assert 'href="/docs"' in page


def test_unknown_theme_falls_back_to_the_first(client):
    assert 'data-theme="indigo"' in client(APP_THEME="purple").get("/").text


def test_home_page_escapes_the_title(client):
    assert "<script>" not in client(APP_TITLE="<script>x</script>").get("/").text


def test_swagger_documents_the_api(client):
    c = client()
    assert c.get("/docs").status_code == 200
    paths = c.get("/openapi.json").json()["paths"]
    assert {"/api/info", "/api/db", "/healthz"} <= set(paths)
    assert "/" not in paths
