"""Cloud accounts (ADR 0029): where the platform may create things, and with which credential.

Each account is a CloudAccount CR. The platform holds one base credential and assumes a role in each
account, so the CR carries no secret: only the role and the ExternalId the API generates. The
aws_account controller proves the trust (AssumeRole with and without the ExternalId) and publishes the
result as conditions; it also publishes the base identity, which the trust policy names as principal.
"""
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from .auth import Principal, current_principal
from .durations import format_time
from .environments import ADMIN_GROUP, OWNER_ANNOTATION, OWNER_NAME_ANNOTATION, can_use, is_owner_or_admin, shared_with
from .journal import Journal
from .state import GROUP, VERSION, AlreadyExists, Conflict, NotFound
from .teams import LABEL as TEAM

CLOUD_ACCOUNTS = "cloudaccounts"
CAPABILITY = "cloud-account"
VENDORS = ("aws",)
NAME = re.compile(r"[a-z]([-a-z0-9]{0,61}[a-z0-9])?")
# Commercial, China and GovCloud partitions; a role path ("role/team/name") is allowed.
ROLE_ARN = re.compile(r"arn:aws(-cn|-us-gov)?:iam::(\d{12}):role/[\w+=,.@/-]{1,512}")
REGION = re.compile(r"[a-z]{2}(-gov)?-[a-z]+-\d")
# Set by `verify`; the controller validates again when it differs from status.observedVerifyRequest.
VERIFY_ANNOTATION = f"{GROUP}/verify-requested-at"
BASE_IDENTITY = "aws-base-identity"


class AccountRequest(BaseModel):
  name: str
  vendor: str
  roleArn: str
  regions: list[str] = []

  @field_validator("name")
  @classmethod
  def check_name(cls, value: str) -> str:
    if not NAME.fullmatch(value):
      raise ValueError("lowercase letters, digits and '-', starting with a letter, at most 63 characters")
    return value

  @field_validator("vendor")
  @classmethod
  def check_vendor(cls, value: str) -> str:
    if value not in VENDORS:
      raise ValueError(f"supported vendors: {', '.join(VENDORS)}")
    return value

  @field_validator("roleArn")
  @classmethod
  def check_role(cls, value: str) -> str:
    if not ROLE_ARN.fullmatch(value):
      raise ValueError("expected an IAM role ARN such as arn:aws:iam::123456789012:role/platform")
    return value

  @field_validator("regions")
  @classmethod
  def check_regions(cls, value: list[str]) -> list[str]:
    for region in value:
      if not REGION.fullmatch(region):
        raise ValueError(f"'{region}' is not an AWS region")
    return sorted(set(value))


class KubeBaseIdentity:
  """The base credential's ARN, which the controller writes to a ConfigMap when it starts."""

  def __init__(self, namespace: str):
    from kubernetes import client

    self.namespace = namespace
    self.core = client.CoreV1Api()
    self._api_exception = client.ApiException

  def arn(self) -> str | None:
    try:
      configmap = self.core.read_namespaced_config_map(BASE_IDENTITY, self.namespace)
    except self._api_exception:
      return None
    return (configmap.data or {}).get("arn") or None


def account_id(role_arn: str) -> str:
  return ROLE_ARN.fullmatch(role_arn).group(2)


def role_key(role_arn: str) -> tuple[str, str, str]:
  """The role an ARN names: IAM role names are unique per account case-insensitively and regardless
  of path, so role/Platform and role/team/platform are the same role as role/platform."""
  match = ROLE_ARN.fullmatch(role_arn)
  if not match:
    return ("", "", role_arn)
  return (match.group(1) or "", match.group(2), role_arn.rsplit("/", 1)[1].lower())


def same_role(obj: dict, key: tuple[str, str, str]) -> bool:
  return role_key(((obj.get("spec") or {}).get("aws") or {}).get("roleArn", "")) == key


def trust_policy(base_arn: str, external_id: str) -> dict:
  """What the account owner applies to the role: trust the base identity, only with our ExternalId."""
  return {
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"AWS": base_arn},
      "Action": "sts:AssumeRole",
      "Condition": {"StringEquals": {"sts:ExternalId": external_id}},
    }],
  }


def manifest(request: AccountRequest, external_id: str, owner: str, owner_name: str | None) -> dict:
  aws = {"roleArn": request.roleArn, "externalId": external_id}
  if request.regions:
    aws["regions"] = request.regions
  annotations = {OWNER_ANNOTATION: owner}
  if owner_name:
    annotations[OWNER_NAME_ANNOTATION] = owner_name
  return {
    "apiVersion": f"{GROUP}/{VERSION}",
    "kind": "CloudAccount",
    "metadata": {"name": request.name, "annotations": annotations},
    "spec": {"vendor": request.vendor, "aws": aws},
  }


def view(obj: dict, base_arn: str | None = None) -> dict:
  """The API view; with base_arn (single reads by the owner or an admin), also the trust policy to
  apply to the role. A team member the account is shared with never gets it: it carries the ExternalId."""
  metadata = obj.get("metadata", {})
  annotations = metadata.get("annotations") or {}
  spec = obj.get("spec") or {}
  aws = spec.get("aws") or {}
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
  requested = annotations.get(VERIFY_ANNOTATION)
  result = {
    "name": metadata.get("name"),
    "vendor": spec.get("vendor"),
    "roleArn": aws.get("roleArn"),
    "regions": aws.get("regions") or [],
    "accountId": status.get("accountId") or (account_id(aws["roleArn"]) if aws.get("roleArn") else None),
    "status": state,
    "message": ready.get("message") if ready else None,
    "callerArn": status.get("callerArn"),
    "lastValidated": status.get("lastValidated"),
    # True until the controller answers the last `verify`: `verify --wait` polls on it.
    "verifyPending": bool(requested) and requested != status.get("observedVerifyRequest"),
    "owner": annotations.get(OWNER_NAME_ANNOTATION),
    "sharedWith": shared_with(obj),
    "createdAt": metadata.get("creationTimestamp"),
  }
  if base_arn and aws.get("externalId"):
    result["trustPolicy"] = trust_policy(base_arn, aws["externalId"])
  return result


def router(state, journal: Journal, base_identity, check_share=None) -> APIRouter:
  """check_share is the environments' rule for adding a team (ADR 0026), shared from app.py."""
  routes = APIRouter(prefix="/v1/cloud/accounts")

  def base_arn() -> str | None:
    return base_identity.arn() if base_identity else None

  def fetch(name: str) -> dict:
    try:
      return state.get(CLOUD_ACCOUNTS, name)
    except NotFound:
      raise HTTPException(404, f"cloud account '{name}' not found")

  def owned(name: str, principal: Principal) -> dict:
    obj = fetch(name)
    if not is_owner_or_admin(obj, principal):
      raise HTTPException(403, f"cloud account '{name}' is not yours")
    return obj

  @routes.post("", status_code=202)
  def create(request: AccountRequest, principal: Principal = Depends(current_principal)):
    base = base_arn()
    if not base:
      raise HTTPException(409, "no AWS base credential: an admin runs 'platform init --target local --aws-profile <profile>' first")
    key = role_key(request.roleArn)
    if any(same_role(obj, key) for obj in state.list(CLOUD_ACCOUNTS)):
      raise HTTPException(409, f"role {request.roleArn} is already registered")
    body = manifest(request, secrets.token_urlsafe(24), principal.sub, principal.email)
    # The ExternalId is not a secret, but it stays out of the journal anyway.
    entry = journal.record("create", "CloudAccount", request.name, {"vendor": request.vendor, "aws": {"roleArn": request.roleArn, "regions": request.regions}}, principal.actor)
    try:
      created = state.create(CLOUD_ACCOUNTS, body)
    except AlreadyExists:
      raise HTTPException(409, f"cloud account '{request.name}' already exists")
    # The kube API has no unique index: a concurrent create of the same role is caught here, and
    # this one steps back (if both step back, both callers retry).
    if any(same_role(obj, key) and obj["metadata"]["name"] != request.name for obj in state.list(CLOUD_ACCOUNTS)):
      try:
        state.delete(CLOUD_ACCOUNTS, request.name, uid=created["metadata"].get("uid"))
      except (NotFound, Conflict):
        pass
      raise HTTPException(409, f"role {request.roleArn} is already registered")
    journal.mark_applied(entry)
    return view(created, base)

  @routes.get("")
  def list_accounts(principal: Principal = Depends(current_principal)):
    everything = ADMIN_GROUP in principal.groups
    items = sorted(state.list(CLOUD_ACCOUNTS), key=lambda obj: obj["metadata"]["name"])
    return {"items": [view(obj) for obj in items if everything or can_use(obj, principal)]}

  @routes.get("/{name}")
  def get(name: str, principal: Principal = Depends(current_principal)):
    obj = fetch(name)
    if not can_use(obj, principal):
      raise HTTPException(403, f"cloud account '{name}' is not yours")
    return view(obj, base_arn() if is_owner_or_admin(obj, principal) else None)

  def change_share(name: str, team: str, principal: Principal, add: bool) -> dict:
    obj = fetch(name)
    if not is_owner_or_admin(obj, principal):
      raise HTTPException(403, f"cloud account '{name}' can only be shared by its owner or {ADMIN_GROUP}")
    current = shared_with(obj)
    if add:
      if check_share:
        check_share([team], principal)
      if team in current:
        return view(obj, base_arn())
      updated = sorted({*current, team})
    else:
      # No membership check: taking access away is always allowed to the owner, even for a deleted team.
      if team not in current:
        raise HTTPException(404, f"cloud account '{name}' is not shared with '{team}'")
      updated = [item for item in current if item != team]
    spec = {key: value for key, value in obj["spec"].items() if key != "sharedWith"}
    if updated:
      spec["sharedWith"] = updated
    obj["spec"] = spec
    entry = journal.record("share" if add else "unshare", "CloudAccount", name, {"team": team}, principal.actor)
    try:
      replaced = state.replace(CLOUD_ACCOUNTS, obj)
    except NotFound:
      raise HTTPException(404, f"cloud account '{name}' not found")
    except Conflict:
      raise HTTPException(409, f"cloud account '{name}' changed while sharing: try again")
    journal.mark_applied(entry)
    return view(replaced, base_arn())

  @routes.put("/{name}/shares/{team}")
  def share(name: str, team: str, principal: Principal = Depends(current_principal)):
    if not TEAM.fullmatch(team):
      raise HTTPException(422, f"'{team}' is not a team name")
    return change_share(name, team, principal, add=True)

  @routes.delete("/{name}/shares/{team}")
  def unshare(name: str, team: str, principal: Principal = Depends(current_principal)):
    return change_share(name, team, principal, add=False)

  @routes.post("/{name}/verify", status_code=202)
  def verify(name: str, principal: Principal = Depends(current_principal)):
    obj = owned(name, principal)
    obj["metadata"].setdefault("annotations", {})[VERIFY_ANNOTATION] = format_time(datetime.now(timezone.utc))
    entry = journal.record("verify", "CloudAccount", name, None, principal.actor)
    try:
      replaced = state.replace(CLOUD_ACCOUNTS, obj)
    except NotFound:
      raise HTTPException(404, f"cloud account '{name}' not found")
    except Conflict:
      raise HTTPException(409, f"cloud account '{name}' changed while verifying: try again")
    journal.mark_applied(entry)
    return view(replaced, base_arn())

  @routes.delete("/{name}", status_code=202)
  def delete(name: str, principal: Principal = Depends(current_principal)):
    obj = owned(name, principal)
    entry = journal.record("delete", "CloudAccount", name, None, principal.actor)
    try:
      state.delete(CLOUD_ACCOUNTS, name, uid=obj["metadata"].get("uid"))
    except NotFound:
      raise HTTPException(404, f"cloud account '{name}' not found")
    except Conflict:
      raise HTTPException(409, f"cloud account '{name}' changed while removing: try again")
    journal.mark_applied(entry)
    return {"name": name, "status": "deleting"}

  return routes
