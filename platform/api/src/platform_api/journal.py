"""Append-only request journal (ADR 0022).

This slice writes JSON Lines to a file on the API volume; the Postgres table arrives with #144.
Each accepted request gets one line before it is applied and one line after (applied: true).
Secrets never reach the file: every record goes through redact() (ADR 0025).
"""
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Journal:
  def __init__(self, path: str | Path):
    self.path = Path(path)
    self.path.parent.mkdir(parents=True, exist_ok=True)
    self._lock = threading.Lock()

  def record(self, action: str, kind: str, name: str, spec: dict | None, actor: str) -> str:
    entry_id = str(uuid.uuid4())
    self._append({
      "id": entry_id,
      "at": _now(),
      "actor": actor,
      "action": action,
      "kind": kind,
      "name": name,
      "spec": redact(spec),
      "applied": False,
    })
    return entry_id

  def mark_applied(self, entry_id: str) -> None:
    self._append({"id": entry_id, "at": _now(), "applied": True})

  def _append(self, entry: dict) -> None:
    line = json.dumps(entry, separators=(",", ":")) + "\n"
    with self._lock, open(self.path, "a", encoding="utf-8") as journal_file:
      journal_file.write(line)
      journal_file.flush()
      os.fsync(journal_file.fileno())


# Keys whose value is a credential, wherever they appear in a record.
SENSITIVE_KEYS = {"privatekeypem", "privatekey", "pem", "clientsecret", "webhooksecret", "token", "password", "secret"}


def redacted(value) -> str:
  """Enough to tell two values apart in an audit, nothing to recover them."""
  digest = hashlib.sha256(str(value).encode()).hexdigest()[:8]
  return f"<redacted, sha256:{digest}>"


def redact(value):
  """A copy with every sensitive value replaced: by key name, and any PEM block whatever its key."""
  if isinstance(value, dict):
    return {key: redacted(item) if key.lower() in SENSITIVE_KEYS and item is not None else redact(item) for key, item in value.items()}
  if isinstance(value, list):
    return [redact(item) for item in value]
  if isinstance(value, str) and "-----BEGIN" in value:
    return redacted(value)
  return value


def _now() -> str:
  return datetime.now(timezone.utc).isoformat(timespec="seconds")
