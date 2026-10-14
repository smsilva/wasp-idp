from datetime import datetime, timezone
from typing import Literal, get_args

from .durations import format_time
from .state import GROUP, VERSION

NO_PROVIDER = "NoProviderForCapability"
# Who asked for the environment (token `sub`), set by the API on create; the CR spec stays the user's intent.
OWNER_ANNOTATION = f"{GROUP}/owner"
# The owner's e-mail, for display only: authorization always goes by OWNER_ANNOTATION (ADR 0026).
OWNER_NAME_ANNOTATION = f"{GROUP}/owner-name"
# The uid of the CloudAccount the API authorized on create (#436): the cloud provider provisions only into
# that exact account, never into one registered again under the same name, nor for a CR written elsewhere.
CLOUD_ACCOUNT_UID_ANNOTATION = f"{GROUP}/cloud-account-uid"
ADMIN_GROUP = "platform-admins"
# The kinds of environment; each can carry a binding policy layer (#329).
Profile = Literal["ephemeral", "shared"]
PROFILES = get_args(Profile)


def manifest(name: str, profile: str, expires_at: str | None, owner: str, owner_name: str | None = None, shared_with: list[str] | None = None, cloud_account: str | None = None, cloud_account_uid: str | None = None) -> dict:
  spec = {"profile": profile}
  if cloud_account:
    spec["cloudAccount"] = cloud_account
  if expires_at:
    spec["expiresAt"] = expires_at
  if shared_with:
    spec["sharedWith"] = sorted(set(shared_with))
  annotations = {OWNER_ANNOTATION: owner}
  if owner_name:
    annotations[OWNER_NAME_ANNOTATION] = owner_name
  if cloud_account_uid:
    annotations[CLOUD_ACCOUNT_UID_ANNOTATION] = cloud_account_uid
  return {
    "apiVersion": f"{GROUP}/{VERSION}",
    "kind": "Environment",
    "metadata": {"name": name, "annotations": annotations},
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


def is_owner_or_admin(obj: dict, principal, annotation: str = OWNER_ANNOTATION) -> bool:
  """True for whoever the annotation names and for platform admins. Environments use the owner
  annotation (delete, share); catalog entities pass their created-by annotation. Without the
  annotation (objects created before it existed), only admins pass."""
  person = (obj.get("metadata", {}).get("annotations") or {}).get(annotation)
  return principal.sub == person or ADMIN_GROUP in principal.groups


def shared_with(obj: dict) -> list[str]:
  return list((obj.get("spec") or {}).get("sharedWith") or [])


def cloud_account(obj: dict) -> str | None:
  """The CloudAccount the environment is provisioned in (#435); None for a local vcluster."""
  return (obj.get("spec") or {}).get("cloudAccount")


def no_vcluster(obj: dict) -> str | None:
  """Why the routes of a vcluster (credentials, kubeconfigs, workloads) do not apply, or None when they do."""
  account = cloud_account(obj)
  if account:
    return f"environment '{obj['metadata']['name']}' runs in cloud account '{account}' and has no vcluster"
  return None


def can_use(obj: dict, principal) -> bool:
  """Owner, admins, and members of a team the environment is shared with (ADR 0026): they get the kubeconfig."""
  return is_owner_or_admin(obj, principal) or bool(set(principal.teams) & set(shared_with(obj)))


def ingress_url(ingress: dict | None) -> str | None:
  """http://*.<domain>:<port>: where the workloads of the environment are reached (ADR 0036)."""
  if not ingress or not ingress.get("domain"):
    return None
  port = ingress.get("port")
  return f"http://*.{ingress['domain']}" + (f":{port}" if port and port != 80 else "")


def view(obj: dict, kubeconfig: str | None = None) -> dict:
  """The API view of an Environment: clients never couple to the CR shape.

  kubeconfigData is the caller's personal kubeconfig (ADR 0028): never in the list, and in the single
  read only when the caller passed can_use. The admin kubeconfig in the status never goes out here.
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
    "cloudAccount": spec.get("cloudAccount"),
    "expiresAt": spec.get("expiresAt"),
    "status": state,
    "message": ready.get("message") if ready else None,
    "port": status.get("port"),
    "ingress": ingress_url(status.get("ingress")),
    # What the environment has in its cloud account (#436): vendor, region and the network.
    "cloud": status.get("cloud"),
    "createdAt": metadata.get("creationTimestamp"),
    "owner": (metadata.get("annotations") or {}).get(OWNER_NAME_ANNOTATION),
    "sharedWith": shared_with(obj),
  }
  if kubeconfig:
    result["kubeconfigData"] = kubeconfig
  return result
