"""A shared Postgres instance seen by its admin (compose, #305).

Every name reaches SQL as sql.Identifier and every value as a parameter or sql.Literal, never
interpolated (ADR 0031). Ownership lives in the instance itself: the role carries the ResourceRequest
as its comment, set in the same transaction that creates it, and a database is the role's only when
the role owns it. CREATE DATABASE cannot run in a transaction, so a database left without its comment
by a crash is still recognised through its owner.
"""
import psycopg
from psycopg import sql

PORT = 5432
ADMIN = "postgres"


class SharedPostgres:
  def __init__(self, host: str, password: str, port: int = PORT, user: str = ADMIN):
    self.host, self.password, self.port, self.user = host, password, port, user

  def _connect(self) -> psycopg.Connection:
    return psycopg.connect(host=self.host, port=self.port, user=self.user, password=self.password, dbname="postgres", autocommit=True, connect_timeout=5)

  def claimed_by(self, name: str) -> str | None:
    """None when neither role nor database exists; the ResourceRequest that owns them; "" when
    something else does (a role without our comment, a database another role owns)."""
    with self._connect() as conn:
      role = conn.execute("SELECT oid, shobj_description(oid, 'pg_authid') FROM pg_roles WHERE rolname = %s", (name,)).fetchone()
      database = conn.execute("SELECT datdba FROM pg_database WHERE datname = %s", (name,)).fetchone()
    if role is None:
      return None if database is None else ""
    if database is not None and database[0] != role[0]:
      return ""
    return role[1] or ""

  def ensure(self, name: str, password: str, owner: str) -> None:
    role = sql.Identifier(name)
    with self._connect() as conn:
      if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone() is None:
        with conn.transaction():
          conn.execute(sql.SQL("CREATE ROLE {} LOGIN").format(role))
          conn.execute(sql.SQL("COMMENT ON ROLE {} IS {}").format(role, sql.Literal(owner)))
      conn.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(role, sql.Literal(password)))
      if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone() is None:
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(role, role))
      conn.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(role, sql.Literal(owner)))
      # Only its own role connects: the other tenants of the instance never see it.
      conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(role))

  def drop(self, name: str) -> None:
    role = sql.Identifier(name)
    with self._connect() as conn:
      conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(role))
      conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(role))
