"""OCIRegistry status (ADR 0037, #365): does the registry answer the Distribution API?

GET https://<host>/v2/ is the version check of the OCI Distribution Spec: 200, or 401 with a
WWW-Authenticate challenge (GHCR asks for a token even to read), means a registry is there. Anything
else, or no answer, is Unreachable. Nothing waits on it: the CI pushes, so a registry Unreachable from
the cluster does not block a build. Pull credentials come with later slices (#367).
"""
import logging
from datetime import datetime, timezone

import httpx

log = logging.getLogger("registry-provider")
TIMEOUT = 10


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


def probe(host: str, http: httpx.Client) -> tuple[bool, str]:
  url = f"https://{host}/v2/"
  try:
    response = http.get(url, timeout=TIMEOUT, follow_redirects=False)
  except httpx.HTTPError as error:
    return False, f"{url}: {error.__class__.__name__}: {error}"
  if response.status_code == 200:
    return True, f"{url} answered 200"
  if response.status_code == 401 and response.headers.get("www-authenticate"):
    return True, f"{url} answered 401 with a token challenge"
  return False, f"{url} answered {response.status_code}: not an OCI registry"


class Reconciler:
  def __init__(self, store, http: httpx.Client, now=utcnow):
    self.store = store
    self.http = http
    self.now = now

  def reconcile(self, obj: dict) -> None:
    if obj["metadata"].get("deletionTimestamp"):
      return
    name = obj["metadata"]["name"]
    ok, message = probe(obj["spec"]["host"], self.http)
    reason = "Verified" if ok else "Unreachable"
    status = "True" if ok else "False"
    current = next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), {})
    if (current.get("status"), current.get("reason"), current.get("message")) == (status, reason, message):
      return
    moment = current.get("lastTransitionTime") if (current.get("status"), current.get("reason")) == (status, reason) else None
    condition = {"type": "Ready", "status": status, "reason": reason, "message": message[:500], "lastTransitionTime": moment or self.now().strftime("%Y-%m-%dT%H:%M:%SZ")}
    self.store.patch_status(name, {"conditions": [condition]})
    log.info("registry %s: %s (%s)", name, reason, message)
