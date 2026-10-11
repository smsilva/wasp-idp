import importlib

from fastapi.testclient import TestClient

import app.main


def client_with_name(monkeypatch, name):
    if name is None:
        monkeypatch.delenv("APP_NAME", raising=False)
    else:
        monkeypatch.setenv("APP_NAME", name)
    return TestClient(importlib.reload(app.main).app)


def test_healthz_returns_ok(monkeypatch):
    client = client_with_name(monkeypatch, None)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_returns_app_name_from_environment(monkeypatch):
    client = client_with_name(monkeypatch, "hello-alpha")
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"app": "hello-alpha", "message": "hello"}


def test_root_falls_back_to_default_name(monkeypatch):
    client = client_with_name(monkeypatch, None)
    assert client.get("/").json()["app"] == "python-service"
