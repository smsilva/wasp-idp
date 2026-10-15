import importlib
import os
import socket

import pytest
from fastapi.testclient import TestClient

import app.main


def free_port() -> int:
    """A port nothing listens on: the connection is refused at once."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def client():
    return TestClient(importlib.reload(app.main).app)


def test_without_host_the_database_is_not_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_HOST", raising=False)
    c = client()
    response = c.get("/api/db")
    assert response.status_code == 200
    assert response.json()["status"] == "not-configured"
    assert "No database configured" in c.get("/").text


def unreachable(monkeypatch):
    monkeypatch.setenv("DATABASE_HOST", "127.0.0.1")
    monkeypatch.setenv("DATABASE_PORT", str(free_port()))
    monkeypatch.setenv("DATABASE_NAME", "app")
    monkeypatch.setenv("DATABASE_USER", "app")
    monkeypatch.setenv("DATABASE_PASSWORD", "s3cret-value")


def test_an_unreachable_database_fails_in_red_without_details_by_default(monkeypatch, caplog):
    unreachable(monkeypatch)
    monkeypatch.delenv("SHOW_DATABASE_DETAILS", raising=False)
    c = client()
    response = c.get("/api/db")
    assert response.status_code == 503
    body = response.json()
    assert (body["status"], body["details"]) == ("failed", False)
    assert set(body) == {"status", "checkedAt", "details"}
    page = c.get("/")
    assert 'data-state="failed"' in page.text
    assert "127.0.0.1" not in page.text
    # The error goes to the log, never the password.
    assert "127.0.0.1" in caplog.text
    assert "s3cret-value" not in caplog.text


def test_details_show_the_target_and_the_error_without_the_password(monkeypatch):
    unreachable(monkeypatch)
    monkeypatch.setenv("SHOW_DATABASE_DETAILS", "true")
    c = client()
    response = c.get("/api/db")
    assert response.status_code == 503
    body = response.json()
    assert (body["status"], body["details"], body["host"]) == ("failed", True, "127.0.0.1")
    assert body["error"]
    assert "s3cret-value" not in response.text
    page = c.get("/")
    assert "Can't reach the database" in page.text
    assert "127.0.0.1" in page.text
    assert "s3cret-value" not in page.text


@pytest.mark.skipif(not os.environ.get("DATABASE_HOST"), reason="needs a PostgreSQL: set DATABASE_HOST, as CI does")
def test_a_reachable_database_connects(monkeypatch):
    monkeypatch.setenv("SHOW_DATABASE_DETAILS", "true")
    c = client()
    body = c.get("/api/db").json()
    assert body["status"] == "connected", body.get("error")
    assert body["serverVersion"]
    assert body["latencyMs"] >= 0
    assert "Connected to PostgreSQL" in c.get("/").text
