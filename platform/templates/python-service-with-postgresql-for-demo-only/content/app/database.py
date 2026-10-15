"""The database check behind the home page and GET /api/db.

The platform sets DATABASE_* from the `db` resource of app-spec.yaml (Score); without DATABASE_HOST
there is nothing to check. Each check opens its own short connection, so the page shows the state at
the moment it loaded: a database that went away turns the page red on the next reload.

Host, user, server address and the driver's error are shown only with SHOW_DATABASE_DETAILS=true: they
help a demo and an attacker alike. The error always goes to the log.
"""
import logging
import os
import time
from datetime import UTC, datetime
from typing import Literal

import psycopg
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# libpq's connect_timeout, in seconds (2 is its minimum).
TIMEOUT = 2

logger = logging.getLogger(__name__)


class DatabaseStatus(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: Literal["connected", "failed", "not-configured"]
    host: str | None = None
    port: int | None = None
    database: str | None = None
    user: str | None = None
    server_version: str | None = None
    server_address: str | None = None
    latency_ms: float | None = None
    error: str | None = None
    checked_at: datetime
    details: bool = False


def show_details() -> bool:
    return os.environ.get("SHOW_DATABASE_DETAILS", "false").lower() == "true"


def check() -> DatabaseStatus:
    """The state of the database; without SHOW_DATABASE_DETAILS, only the state and the latency."""
    status = _connect()
    if status.status == "failed":
        logger.warning("database check failed: %s:%s/%s as %s: %s", status.host, status.port, status.database, status.user, status.error)
    if show_details():
        return status.model_copy(update={"details": True})
    return DatabaseStatus(status=status.status, latency_ms=status.latency_ms, checked_at=status.checked_at)


def _connect() -> DatabaseStatus:
    host = os.environ.get("DATABASE_HOST") or None
    target = {
        "host": host,
        "port": int(os.environ.get("DATABASE_PORT") or 5432),
        "database": os.environ.get("DATABASE_NAME") or None,
        "user": os.environ.get("DATABASE_USER") or None,
        "checked_at": datetime.now(UTC),
    }
    if host is None:
        return DatabaseStatus(status="not-configured", **target)
    password = os.environ.get("DATABASE_PASSWORD") or ""
    started = time.perf_counter()
    try:
        with psycopg.connect(
            host=host,
            port=target["port"],
            dbname=target["database"],
            user=target["user"],
            password=password,
            connect_timeout=TIMEOUT,
            application_name=os.environ.get("APP_NAME", "python-service"),
        ) as connection:
            version, address, port = connection.execute(
                "SELECT current_setting('server_version'), host(inet_server_addr()), inet_server_port()"
            ).fetchone()
    except psycopg.Error as error:
        message = str(error).strip() or type(error).__name__
        if password:
            message = message.replace(password, "***")
        return DatabaseStatus(status="failed", error=message, **target)
    latency = round((time.perf_counter() - started) * 1000, 1)
    return DatabaseStatus(
        status="connected",
        server_version=version,
        server_address=f"{address}:{port}" if address else None,
        latency_ms=latency,
        **target,
    )
