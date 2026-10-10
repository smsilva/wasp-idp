from datetime import datetime, timezone

from .durations import format_time
from .state import GROUP, VERSION

NO_PROVIDER = "NoProviderForCapability"


def manifest(name: str, profile: str, expires_at: str | None) -> dict:
  spec = {"profile": profile}
  if expires_at:
    spec["expiresAt"] = expires_at
  return {
    "apiVersion": f"{GROUP}/{VERSION}",
    "kind": "Environment",
    "metadata": {"name": name},
    "spec": spec,
  }


def no_provider_status() -> dict:
  return {
    "conditions": [{
      "type": "Ready",
      "status": "False",
      "reason": NO_PROVIDER,
      "message": "no provider has claimed the environment capability yet",
      "lastTransitionTime": format_time(datetime.now(timezone.utc)),
    }]
  }


def view(obj: dict) -> dict:
  """The API view of an Environment: clients never couple to the CR shape."""
  metadata = obj.get("metadata", {})
  spec = obj.get("spec", {})
  status = obj.get("status") or {}
  ready = next((c for c in status.get("conditions", []) if c.get("type") == "Ready"), None)
  if metadata.get("deletionTimestamp"):
    state = "deleting"
  elif ready is None:
    state = "pending"
  elif ready.get("status") == "True":
    state = "ready"
  else:
    state = ready.get("reason") or "pending"
  return {
    "name": metadata.get("name"),
    "profile": spec.get("profile"),
    "expiresAt": spec.get("expiresAt"),
    "status": state,
    "message": ready.get("message") if ready else None,
    "kubeconfig": status.get("kubeconfig"),
    "createdAt": metadata.get("creationTimestamp"),
  }
