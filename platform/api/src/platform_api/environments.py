from datetime import datetime, timezone

from .durations import format_time
from .state import GROUP, VERSION

NO_PROVIDER = "NoProviderForCapability"
# Who asked for the environment (token `sub`), set by the API on create; the CR spec stays the user's intent.
OWNER_ANNOTATION = f"{GROUP}/owner"
ADMIN_GROUP = "platform-admins"


def manifest(name: str, profile: str, expires_at: str | None, owner: str) -> dict:
  spec = {"profile": profile}
  if expires_at:
    spec["expiresAt"] = expires_at
  return {
    "apiVersion": f"{GROUP}/{VERSION}",
    "kind": "Environment",
    "metadata": {"name": name, "annotations": {OWNER_ANNOTATION: owner}},
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


def can_read_credentials(obj: dict, principal) -> bool:
  """The kubeconfig is admin access to the environment: only its owner and platform admins get it."""
  owner = (obj.get("metadata", {}).get("annotations") or {}).get(OWNER_ANNOTATION)
  return principal.sub == owner or ADMIN_GROUP in principal.groups


def view(obj: dict, with_kubeconfig: bool = False) -> dict:
  """The API view of an Environment: clients never couple to the CR shape.

  kubeconfigData is a credential: never in the list, and in the single read only when the caller
  passed can_read_credentials.
  """
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
  result = {
    "name": metadata.get("name"),
    "profile": spec.get("profile"),
    "expiresAt": spec.get("expiresAt"),
    "status": state,
    "message": ready.get("message") if ready else None,
    "port": status.get("port"),
    "createdAt": metadata.get("creationTimestamp"),
  }
  if with_kubeconfig and status.get("kubeconfigData"):
    result["kubeconfigData"] = status["kubeconfigData"]
  return result
