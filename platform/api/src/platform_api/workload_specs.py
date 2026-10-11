"""The Workload Spec (#291, ADR 0033): the app-spec.yaml (Score) of a version, kept in the version index.

validate runs the gate of the build (wasp_score) on a local file, before any build: the schema, the
resource types of the platform, each resource id in the catalog. The spec of a component is read from
its Version, where the scm_github provider stored it: a version indexed before #291 has none
(SpecNotIndexed). validate is open to any signed-in user; the spec of a component goes only to members
of its owner team and platform-admins, since a Score may carry plain values from a private repo.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from wasp_score import RESOURCE_TYPES, check

from .auth import Principal, current_principal
from .builds import COMPONENTS, VERSIONS
from .environments import ADMIN_GROUP
from .state import NotFound

RESOURCES = "resources"
# The same bound as the artifact the build reads: a Score is a few KiB.
CONTENT_MAX = 64 * 1024


class ValidateRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  content: str = Field(max_length=CONTENT_MAX)


def spec_view(obj: dict) -> dict:
  spec = obj.get("spec", {})
  return {
    "kind": "WorkloadSpec",
    **{field: spec.get(field) for field in ("component", "version", "commit", "branch", "image", "digest", "createdAt")},
    "appSpec": spec.get("appSpec"),
  }


def router(state, resource_types=RESOURCE_TYPES) -> APIRouter:
  routes = APIRouter(prefix="/v1")

  def resource_exists(name: str) -> bool:
    try:
      state.get(RESOURCES, name)
    except NotFound:
      return False
    return True

  @routes.post("/workload-specs:validate")
  def validate(request: ValidateRequest, principal: Principal = Depends(current_principal)):
    result = check(request.content, resource_exists, resource_types)
    # An invalid spec is the answer, not a failed request.
    return {"valid": result.valid, "errors": result.errors, "resources": result.resources}

  @routes.get("/catalog/components/{component}/spec")
  def get(component: str, version: str | None = None, branch: str | None = None, principal: Principal = Depends(current_principal)):
    if version is not None and branch is not None:
      raise HTTPException(422, f"spec of '{component}': version and branch are exclusive")
    try:
      owner = (state.get(COMPONENTS, component).get("spec") or {}).get("owner")
    except NotFound:
      raise HTTPException(404, f"component '{component}' not found")
    if not (owner in principal.teams or ADMIN_GROUP in principal.groups):
      raise HTTPException(403, f"spec of '{component}': only members of its owner team ({owner or 'none'}) and {ADMIN_GROUP} read it")
    versions = [obj for obj in state.list(VERSIONS) if obj["spec"].get("component") == component]
    if version is not None:
      found = [obj for obj in versions if obj["spec"].get("version", "").lower() == version.lower()]
      wanted = f"version {version}"
    elif branch is not None:
      found = [obj for obj in versions if obj["spec"].get("branch") == branch]
      wanted = f"version built from branch '{branch}'"
    else:
      found = versions
      wanted = "version"
    if not found:
      raise HTTPException(404, f"spec of '{component}': no {wanted} in the index")
    newest = max(found, key=lambda obj: (obj["spec"].get("createdAt") or "", obj["metadata"]["name"]))
    if newest["spec"].get("appSpec") is None:
      raise HTTPException(409, f"SpecNotIndexed: {component} {newest['spec'].get('version')} was indexed before the version index kept the spec: build it again under a new version")
    return spec_view(newest)

  return routes
