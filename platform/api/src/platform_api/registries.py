"""OCI registries (ADR 0037, #365): where a build pushes, chosen per build.

An OCIRegistry names a host and a namespace (the org of GHCR). platform-admins add and remove them;
reading is open to any signed-in user, who picks one in `build create --registry`. At most one is the
default, the registry of a build without --registry; the API is the only writer, so it keeps that.
The registry controller checks that <host>/v2/ answers and sets Ready; nothing here waits for it.

A ghcr registry is written by the run's GITHUB_TOKEN, which pushes only to the GHCR of the org that
owns the repo: `push_target` refuses another namespace before the dispatch. `--scm-connection` fills
vendor, host and namespace from a github connection once, at creation: the registry keeps no reference
to it, so removing the connection leaves the registry alone.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from .auth import Principal, current_principal
from .environments import ADMIN_GROUP
from .journal import Journal
from .scm import PLURAL as CONNECTIONS
from .state import GROUP, VERSION, AlreadyExists, Conflict, NotFound

REGISTRIES = "ociregistries"
VERSIONS = "versions"
KIND = "OCIRegistry"
VENDORS = ("ghcr",)
# Hosts each vendor is fixed to: the CI credential of the vendor writes only there.
FIXED_HOSTS = {"ghcr": "ghcr.io"}
NAME = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")
HOST = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?(\.[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?)+(:[0-9]{1,5})?")
NAMESPACE = re.compile(r"[a-z0-9]([-a-z0-9_.]{0,61}[a-z0-9])?")


class RegistryRequest(BaseModel):
  model_config = ConfigDict(extra="forbid", populate_by_name=True)

  name: str
  vendor: str | None = None
  host: str | None = None
  namespace: str | None = None
  default: bool = False
  scmConnection: str | None = None

  @field_validator("name")
  @classmethod
  def check_name(cls, value: str) -> str:
    if not NAME.fullmatch(value):
      raise ValueError("lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters")
    return value

  @field_validator("vendor")
  @classmethod
  def check_vendor(cls, value: str | None) -> str | None:
    if value is not None and value not in VENDORS:
      raise ValueError(f"supported vendors: {', '.join(VENDORS)}")
    return value

  @field_validator("host")
  @classmethod
  def check_host(cls, value: str | None) -> str | None:
    if value is not None and not HOST.fullmatch(value):
      raise ValueError("a host name such as ghcr.io, with an optional :port")
    return value

  @field_validator("namespace")
  @classmethod
  def check_namespace(cls, value: str | None) -> str | None:
    if value is not None:
      value = value.lower()
      if not NAMESPACE.fullmatch(value):
        raise ValueError("lowercase letters, digits, '-', '_' and '.', at most 63 characters")
    return value

  def source(self) -> tuple[str, str, str] | None:
    """vendor, host and namespace given explicitly; None with scmConnection. Refusals as 422."""
    if self.scmConnection is not None:
      if self.vendor or self.host or self.namespace:
        raise HTTPException(422, "give either scmConnection or vendor and namespace, not both")
      return None
    if not self.vendor or not self.namespace:
      raise HTTPException(422, "vendor and namespace are required without scmConnection")
    fixed = FIXED_HOSTS.get(self.vendor)
    if fixed and self.host not in (None, fixed):
      raise HTTPException(422, f"host: a {self.vendor} registry is {fixed}")
    if not (self.host or fixed):
      raise HTTPException(422, f"host is required for a {self.vendor} registry")
    return self.vendor, self.host or fixed, self.namespace


def ready_of(obj: dict) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), None)


def address(obj: dict) -> str:
  spec = obj.get("spec") or {}
  return f"{spec.get('host')}/{spec.get('namespace')}"


def view(obj: dict) -> dict:
  spec = obj.get("spec") or {}
  ready = ready_of(obj)
  if obj["metadata"].get("deletionTimestamp"):
    state = "deleting"
  elif ready is None:
    state = "pending"
  else:
    state = "ready" if ready.get("status") == "True" else ready.get("reason") or "pending"
  return {
    "kind": KIND,
    "name": obj["metadata"]["name"],
    "vendor": spec.get("vendor"),
    "host": spec.get("host"),
    "namespace": spec.get("namespace"),
    "address": address(obj),
    "default": bool(spec.get("default")),
    "pullMode": (spec.get("pull") or {}).get("mode") or "anonymous",
    "status": state,
    "message": ready.get("message") if ready else None,
    "createdAt": obj["metadata"].get("creationTimestamp"),
  }


def default_of(state) -> dict | None:
  defaults = sorted((obj for obj in state.list(REGISTRIES) if (obj.get("spec") or {}).get("default")), key=lambda obj: obj["metadata"]["name"])
  return defaults[0] if defaults else None


def push_target(state, component: str, repo: str, name: str | None) -> tuple[str, str]:
  """The registry a build of the component pushes to and the image: refused before any Build."""
  if name is None:
    registry = default_of(state)
    if registry is None:
      raise HTTPException(409, f"build of '{component}': no default registry (NoDefaultRegistry): an admin runs 'platform registry add <name> --scm-connection <connection> --default', or pass --registry")
  else:
    try:
      registry = state.get(REGISTRIES, name)
    except NotFound:
      raise HTTPException(422, f"build of '{component}': registry '{name}' not found")
  spec = registry["spec"]
  org = repo.split("/")[0].lower()
  if spec.get("vendor") == "ghcr" and spec.get("namespace") != org:
    raise HTTPException(422, f"build of '{component}': registry {registry['metadata']['name']} ({address(registry)}) is not writable by the CI of {repo}: GITHUB_TOKEN pushes only to ghcr.io/{org} (RegistryNotWritableByCI)")
  return registry["metadata"]["name"], f"{address(registry)}/{component}"


def router(state, journal: Journal) -> APIRouter:
  routes = APIRouter(prefix="/v1/registries")

  def admin(principal: Principal, verb: str) -> None:
    if ADMIN_GROUP not in principal.groups:
      raise HTTPException(403, f"{verb} a registry requires group '{ADMIN_GROUP}'")

  def existing(name: str) -> dict:
    try:
      return state.get(REGISTRIES, name)
    except NotFound:
      raise HTTPException(404, f"registry '{name}' not found")

  def from_connection(name: str) -> tuple[str, str, str]:
    try:
      connection = state.get(CONNECTIONS, name)
    except NotFound:
      raise HTTPException(422, f"scm connection '{name}' not found")
    spec = connection.get("spec") or {}
    org = (spec.get("github") or {}).get("org")
    if spec.get("vendor") != "github" or not org:
      raise HTTPException(422, f"scm connection '{name}' is not a github connection with an org")
    return "ghcr", FIXED_HOSTS["ghcr"], org.lower()

  def clear_default(keep: str) -> None:
    """The API keeps at most one default: the previous one stops being it."""
    for obj in state.list(REGISTRIES):
      if obj["metadata"]["name"] != keep and (obj.get("spec") or {}).get("default"):
        obj["spec"]["default"] = False
        try:
          state.replace(REGISTRIES, obj)
        except (NotFound, Conflict):
          pass

  @routes.post("", status_code=201)
  def create(request: RegistryRequest, principal: Principal = Depends(current_principal)):
    admin(principal, "adding")
    vendor, host, namespace = request.source() or from_connection(request.scmConnection)
    spec = {"vendor": vendor, "host": host, "namespace": namespace, "default": request.default, "pull": {"mode": "anonymous"}}
    same = next((obj for obj in state.list(REGISTRIES) if address(obj) == f"{host}/{namespace}"), None)
    if same is not None:
      raise HTTPException(409, f"{host}/{namespace} is already registry '{same['metadata']['name']}'")
    entry = journal.record("create", KIND, request.name, spec, principal.actor)
    body = {"apiVersion": f"{GROUP}/{VERSION}", "kind": KIND, "metadata": {"name": request.name}, "spec": spec}
    try:
      created = state.create(REGISTRIES, body)
    except AlreadyExists:
      raise HTTPException(409, f"registry '{request.name}' already exists")
    if request.default:
      clear_default(request.name)
    journal.mark_applied(entry)
    return view(created)

  @routes.get("")
  def list_registries(principal: Principal = Depends(current_principal)):
    return {"items": [view(obj) for obj in sorted(state.list(REGISTRIES), key=lambda obj: obj["metadata"]["name"])]}

  @routes.get("/{name}")
  def get(name: str, principal: Principal = Depends(current_principal)):
    return view(existing(name))

  @routes.put("/{name}/default")
  def set_default(name: str, principal: Principal = Depends(current_principal)):
    admin(principal, "changing the default of")
    obj = existing(name)
    entry = journal.record("set-default", KIND, name, None, principal.actor)
    obj["spec"]["default"] = True
    try:
      replaced = state.replace(REGISTRIES, obj)
    except NotFound:
      raise HTTPException(404, f"registry '{name}' not found")
    except Conflict:
      raise HTTPException(409, f"registry '{name}' changed meanwhile: try again")
    clear_default(name)
    journal.mark_applied(entry)
    return view(replaced)

  @routes.delete("/{name}", status_code=202)
  def delete(name: str, principal: Principal = Depends(current_principal)):
    admin(principal, "removing")
    obj = existing(name)
    # A Version names its registry: the pull of later slices resolves it by that name.
    users = sorted(item["metadata"]["name"] for item in state.list(VERSIONS) if (item.get("spec") or {}).get("registry") == name)
    if users:
      shown = ", ".join(users[:3]) + (f" and {len(users) - 3} more" if len(users) > 3 else "")
      raise HTTPException(409, f"registry '{name}' holds {len(users)} version(s) of the index ({shown}): it stays")
    entry = journal.record("delete", KIND, name, None, principal.actor)
    try:
      state.delete(REGISTRIES, name, uid=obj["metadata"].get("uid"))
    except NotFound:
      raise HTTPException(404, f"registry '{name}' not found")
    journal.mark_applied(entry)
    return {"name": name, "status": "deleting"}

  return routes
