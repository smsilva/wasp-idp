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
from .environments import ADMIN_GROUP, OWNER_ANNOTATION, OWNER_NAME_ANNOTATION, is_owner_or_admin
from .journal import Journal
from .state import GROUP, VERSION, AlreadyExists, Conflict, NotFound

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
  """The API view; with base_arn (single reads), also the trust policy to apply to the role."""
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
    "createdAt": metadata.get("creationTimestamp"),
  }
  if base_arn and aws.get("externalId"):
    result["trustPolicy"] = trust_policy(base_arn, aws["externalId"])
  return result


def router(state, journal: Journal, base_identity) -> APIRouter:
  routes = APIRouter(prefix="/v1/cloud/accounts")

  def base_arn() -> str | None:
    return base_identity.arn() if base_identity else None

  def owned(name: str, principal: Principal) -> dict:
    try:
      obj = state.get(CLOUD_ACCOUNTS, name)
    except NotFound:
      raise HTTPException(404, f"cloud account '{name}' not found")
    if not is_owner_or_admin(obj, principal):
      raise HTTPException(403, f"cloud account '{name}' is not yours")
    return obj

  @routes.post("", status_code=202)
  def create(request: AccountRequest, principal: Principal = Depends(current_principal)):
    base = base_arn()
    if not base:
      raise HTTPException(409, "no AWS base credential: an admin runs 'platform init --target local --aws-profile <profile>' first")
    taken = next((obj for obj in state.list(CLOUD_ACCOUNTS) if ((obj.get("spec") or {}).get("aws") or {}).get("roleArn") == request.roleArn), None)
    if taken:
      raise HTTPException(409, f"role {request.roleArn} is already registered")
    body = manifest(request, secrets.token_urlsafe(24), principal.sub, principal.email)
    # The ExternalId is not a secret, but it stays out of the journal anyway.
    entry = journal.record("create", "CloudAccount", request.name, {"vendor": request.vendor, "aws": {"roleArn": request.roleArn, "regions": request.regions}}, principal.actor)
    try:
      created = state.create(CLOUD_ACCOUNTS, body)
    except AlreadyExists:
      raise HTTPException(409, f"cloud account '{request.name}' already exists")
    journal.mark_applied(entry)
    return view(created, base)

  @routes.get("")
  def list_accounts(principal: Principal = Depends(current_principal)):
    everything = ADMIN_GROUP in principal.groups
    items = sorted(state.list(CLOUD_ACCOUNTS), key=lambda obj: obj["metadata"]["name"])
    return {"items": [view(obj) for obj in items if everything or is_owner_or_admin(obj, principal)]}

  @routes.get("/{name}")
  def get(name: str, principal: Principal = Depends(current_principal)):
    return view(owned(name, principal), base_arn())

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
