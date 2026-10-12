"""The binding policy of an environment (ADR 0022, 0031, #305): which mode makes each resource there.

The environment layer is one BindingPolicy per environment, env-<name>, owned by the Environment (it
goes with it). The profile layer is one per profile, profile-<profile> (spec.profile, #329). The
Forager reads them in that order, then the platform default (neither spec.environment nor
spec.profile, installed by `platform init`). Only platform-admins write them, since they decide where
data lives; whoever uses the environment reads all three, to see how a resource will resolve. An
empty list removes a policy.
"""
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .auth import Principal, current_principal
from .environments import ADMIN_GROUP, PROFILES, can_use
from .journal import Journal
from .state import ENVIRONMENTS, GROUP, VERSION, AlreadyExists, Conflict, NotFound

POLICIES = "bindingpolicies"
# Names the Forager turns into manifests and SQL: checked here, and again there (ADR 0031).
LABEL = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")
HOST = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?(\.[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?)*")
PORT = re.compile(r"[0-9]{1,5}")
SQL_NAME = re.compile(r"[a-z_][a-z0-9_-]{0,62}")
# bind points at something that exists: its values, and a bindable Secret of platform-resources
# holding the password (#306). The developer never passes the credential.
BIND_PARAMS = (("secretRef", LABEL), ("host", HOST), ("database", SQL_NAME), ("username", SQL_NAME))


def policy_name(environment: str) -> str:
  return f"env-{environment}"


def profile_policy_name(profile: str) -> str:
  return f"profile-{profile}"


def scope(policy: dict) -> tuple[str | None, str | None]:
  spec = policy.get("spec") or {}
  return (spec.get("environment") or None, spec.get("profile") or None)


def items(policies: list[dict]) -> list[dict]:
  return [item for policy in policies for item in (policy.get("spec") or {}).get("provisioners") or []]


class Provisioner(BaseModel):
  model_config = ConfigDict(extra="forbid", populate_by_name=True)

  type: str
  klass: str | None = Field(default=None, alias="class")
  id: str | None = None
  mode: Literal["provision", "compose", "bind"]
  params: dict[str, str] = {}

  @field_validator("type", "klass", "id")
  @classmethod
  def check_name(cls, value: str | None) -> str | None:
    if value is not None and not LABEL.fullmatch(value):
      raise ValueError(f"'{value}' is not a valid name")
    return value

  @model_validator(mode="after")
  def check_params(self):
    # compose needs the shared instance it composes into: there is no implicit one.
    if self.mode == "compose" and not LABEL.fullmatch(self.params.get("instance", "")):
      raise ValueError("compose needs params.instance, the shared instance (for example shared-pg)")
    if self.mode == "bind":
      for key, pattern in BIND_PARAMS:
        if not pattern.fullmatch(self.params.get(key, "")):
          raise ValueError(f"bind needs a valid params.{key} (secretRef, host, database and username; port is 5432 by default)")
      if not PORT.fullmatch(self.params.get("port", "5432")):
        raise ValueError("bind needs a valid params.port")
    return self

  def item(self) -> dict:
    return self.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True)


class PolicyRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  provisioners: list[Provisioner] = Field(max_length=32)


def view(environment: str, own: dict | None, profile: str | None, profile_policies: list[dict], defaults: list[dict]) -> dict:
  return {
    "kind": "BindingPolicy",
    "environment": environment,
    "provisioners": items([own] if own else []),
    "profile": {"name": profile, "provisioners": items(profile_policies)},
    "default": items(defaults),
  }


def profile_view(profile: str, policies: list[dict], defaults: list[dict]) -> dict:
  return {"kind": "BindingPolicy", "profile": profile, "provisioners": items(policies), "default": items(defaults)}


def router(state, journal: Journal) -> APIRouter:
  routes = APIRouter(prefix="/v1")

  def environment_of(name: str) -> dict:
    try:
      return state.get(ENVIRONMENTS, name)
    except NotFound:
      raise HTTPException(404, f"environment '{name}' not found")

  def current(name: str) -> dict | None:
    try:
      return state.get(POLICIES, policy_name(name))
    except NotFound:
      return None

  def of(environment: str | None, profile: str | None) -> list[dict]:
    policies = [obj for obj in state.list(POLICIES) if scope(obj) == (environment, profile)]
    return sorted(policies, key=lambda obj: obj["metadata"]["name"])

  def defaults() -> list[dict]:
    return of(None, None)

  def environment_view(name: str, own: dict | None, environment: dict) -> dict:
    profile = (environment.get("spec") or {}).get("profile")
    return view(name, own, profile, of(None, profile) if profile else [], defaults())

  def known(profile: str) -> str:
    if profile not in PROFILES:
      raise HTTPException(404, f"profile '{profile}' not found (profiles: {', '.join(PROFILES)})")
    return profile

  @routes.get("/environments/{name}/binding-policy")
  def get(name: str, principal: Principal = Depends(current_principal)):
    environment = environment_of(name)
    if not can_use(environment, principal):
      raise HTTPException(403, f"environment '{name}': only its owner, the teams it is shared with and {ADMIN_GROUP} read its policy")
    return environment_view(name, current(name), environment)

  @routes.put("/environments/{name}/binding-policy")
  def put(name: str, request: PolicyRequest, principal: Principal = Depends(current_principal)):
    if ADMIN_GROUP not in principal.groups:
      raise HTTPException(403, f"the binding policy of an environment is set by {ADMIN_GROUP}")
    environment = environment_of(name)
    items = [provisioner.item() for provisioner in request.provisioners]
    existing = current(name)
    entry = journal.record("set-policy", "BindingPolicy", policy_name(name), {"environment": name, "provisioners": items}, principal.actor)
    try:
      if not items:
        if existing is not None:
          state.delete(POLICIES, policy_name(name), existing["metadata"].get("uid"))
        saved = None
      elif existing is None:
        saved = state.create(POLICIES, {
          "apiVersion": f"{GROUP}/{VERSION}",
          "kind": "BindingPolicy",
          "metadata": {
            "name": policy_name(name),
            "labels": {f"{GROUP}/environment": name},
            "ownerReferences": [{"apiVersion": f"{GROUP}/{VERSION}", "kind": "Environment", "name": name, "uid": environment["metadata"]["uid"]}],
          },
          "spec": {"environment": name, "provisioners": items},
        })
      else:
        saved = state.replace(POLICIES, {**existing, "spec": {"environment": name, "provisioners": items}})
    except (AlreadyExists, Conflict, NotFound):
      raise HTTPException(409, f"the policy of '{name}' changed while saving: try again")
    journal.mark_applied(entry)
    return environment_view(name, saved, environment)

  @routes.get("/profiles/{profile}/binding-policy")
  def get_profile(profile: str, principal: Principal = Depends(current_principal)):
    return profile_view(known(profile), of(None, profile), defaults())

  @routes.put("/profiles/{profile}/binding-policy")
  def put_profile(profile: str, request: PolicyRequest, principal: Principal = Depends(current_principal)):
    if ADMIN_GROUP not in principal.groups:
      raise HTTPException(403, f"the binding policy of a profile is set by {ADMIN_GROUP}")
    known(profile)
    items_ = [provisioner.item() for provisioner in request.provisioners]
    name = profile_policy_name(profile)
    try:
      existing = state.get(POLICIES, name)
    except NotFound:
      existing = None
    entry = journal.record("set-policy", "BindingPolicy", name, {"profile": profile, "provisioners": items_}, principal.actor)
    spec = {"profile": profile, "provisioners": items_}
    try:
      if not items_:
        if existing is not None:
          state.delete(POLICIES, name, existing["metadata"].get("uid"))
      elif existing is None:
        state.create(POLICIES, {
          "apiVersion": f"{GROUP}/{VERSION}",
          "kind": "BindingPolicy",
          "metadata": {"name": name, "labels": {f"{GROUP}/profile": profile}},
          "spec": spec,
        })
      else:
        state.replace(POLICIES, {**existing, "spec": spec})
    except (AlreadyExists, Conflict, NotFound):
      raise HTTPException(409, f"the policy of profile '{profile}' changed while saving: try again")
    journal.mark_applied(entry)
    return profile_view(profile, of(None, profile), defaults())

  return routes
