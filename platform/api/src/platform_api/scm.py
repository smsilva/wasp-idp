"""SCM connections (ADR 0025): the code platforms where the platform creates repos.

Only platform-admins manage them. On GitHub the App is created by the manifest flow: the browser takes
the manifest to GitHub, GitHub redirects back to the API with a code, and the API trades the code for
the App's private key, which goes straight to the SecretStore. The browser routes carry no JWT: a
single-use `state`, created by an authenticated admin, is what protects them.
"""
import html
import json
import re
import secrets as tokens
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, field_validator

from .auth import Principal, require_group
from .catalog import LABEL
from .durations import format_time
from .environments import ADMIN_GROUP
from .journal import Journal
from .state import GROUP, VERSION, AlreadyExists, Conflict, NotFound

PLURAL = "scmconnections"
KIND = "ScmConnection"
VERIFY_ANNOTATION = f"{GROUP}/verify-requested-at"
# Set when the manifest flow created the App: only then does removing the connection point at deleting it.
APP_CREATED_ANNOTATION = f"{GROUP}/app-created-by-platform"
# GitHub login rules: alphanumerics and single hyphens, at most 39 characters.
ORG = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
CODE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
STATE_TTL = 600
GITHUB_API = "https://api.github.com"
# What the platform does on the org (ADR 0025); `actions` triggers and reads the build workflow (#206).
PERMISSIONS = {
  "administration": "write",
  "contents": "write",
  "workflows": "write",
  "pull_requests": "write",
  "actions": "write",
  "metadata": "read",
}
HOMEPAGE = "https://github.com/smsilva/wasp-idp"


class ConnectionRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  name: str
  vendor: Literal["github"]
  org: str
  default: bool = False
  # An App that already exists (--app-id and --private-key-file): skips the manifest flow.
  appId: int | None = None
  privateKeyPem: str | None = None

  @field_validator("name")
  @classmethod
  def check_name(cls, value: str) -> str:
    if not LABEL.fullmatch(value):
      raise ValueError("lowercase letters, digits and '-', starting and ending with a letter or digit, at most 63 characters")
    return value

  @field_validator("org")
  @classmethod
  def check_org(cls, value: str) -> str:
    if not ORG.fullmatch(value) or "--" in value:
      raise ValueError("a GitHub organization login")
    return value

  @field_validator("appId")
  @classmethod
  def check_app_id(cls, value: int | None) -> int | None:
    if value is not None and value <= 0:
      raise ValueError("a positive integer")
    return value

  @field_validator("privateKeyPem")
  @classmethod
  def check_pem(cls, value: str | None) -> str | None:
    if value is not None and not ("-----BEGIN" in value and "PRIVATE KEY-----" in value):
      raise ValueError("a PEM private key")
    return value


class States:
  """Single-use states of the manifest flow, in the memory of the one API replica: a restart only
  makes an admin run `scm connection add` again."""

  def __init__(self, ttl: int = STATE_TTL, clock=time.monotonic):
    self.ttl = ttl
    self.clock = clock
    self._items: dict[str, tuple[str, str, float]] = {}
    self._lock = threading.Lock()

  def issue(self, name: str, actor: str) -> str:
    value = tokens.token_urlsafe(32)
    with self._lock:
      now = self.clock()
      self._items = {key: item for key, item in self._items.items() if item[2] > now}
      self._items[value] = (name, actor, now + self.ttl)
    return value

  def peek(self, value: str, name: str) -> str | None:
    """The actor that issued it, while valid for this connection; the state stays usable."""
    with self._lock:
      item = self._items.get(value)
    if item and item[0] == name and item[2] > self.clock():
      return item[1]
    return None

  def consume(self, value: str, name: str) -> str | None:
    with self._lock:
      item = self._items.get(value)
      if not item or item[0] != name:
        return None
      del self._items[value]
    return item[1] if item[2] > self.clock() else None


def condition(reason: str, message: str, ready: bool = False) -> dict:
  return {
    "type": "Ready",
    "status": "True" if ready else "False",
    "reason": reason,
    "message": message,
    "lastTransitionTime": format_time(datetime.now(timezone.utc)),
  }


def secret_name(name: str) -> str:
  return f"scm-{name}"


def ready_of(obj: dict) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), None)


def status_of(obj: dict) -> str:
  ready = ready_of(obj)
  if ready is None:
    return "pending"
  if ready.get("status") == "True":
    return "ready"
  return ready.get("reason") or "pending"


def install_url(slug: str) -> str:
  return f"https://github.com/apps/{slug}/installations/new"


def view(obj: dict) -> dict:
  """The API view, without any credential: the Secret name is not even shown."""
  spec = obj.get("spec") or {}
  github = spec.get("github") or {}
  status = obj.get("status") or {}
  ready = ready_of(obj)
  state = status_of(obj)
  requested = (obj["metadata"].get("annotations") or {}).get(VERIFY_ANNOTATION)
  result = {
    "name": obj["metadata"]["name"],
    "vendor": spec.get("vendor"),
    "org": github.get("org"),
    "default": bool(spec.get("default")),
    "status": state,
    "message": ready.get("message") if ready else None,
    "appId": github.get("appId"),
    "appSlug": github.get("appSlug"),
    "installationId": github.get("installationId"),
    "permissions": status.get("permissions") or {},
    "repositorySelection": status.get("repositorySelection"),
    "lastValidated": status.get("lastValidated"),
    # True until the controller answers the last verify request (the CLI's `verify --wait`).
    "verifying": bool(spec.get("credentialRef") and requested and requested != status.get("observedVerifyRequest")),
    "createdAt": obj["metadata"].get("creationTimestamp"),
  }
  if state == "NotInstalled" and github.get("appSlug"):
    result["installUrl"] = install_url(github["appSlug"])
  return result


def manifest(name: str, org: str, public_url: str) -> dict:
  """The GitHub App manifest: private, no webhook, the permissions of PERMISSIONS."""
  base = f"{public_url}/v1/scm/connections/{name}/github"
  return {
    "name": f"{org}-platform",
    "url": HOMEPAGE,
    "redirect_url": f"{base}/callback",
    "setup_url": f"{base}/installed",
    "setup_on_update": True,
    "public": False,
    "hook_attributes": {"url": HOMEPAGE, "active": False},
    "default_permissions": PERMISSIONS,
  }


def page(title: str, message: str, ok: bool, extra: str = "") -> HTMLResponse:
  """The browser pages of the manifest flow, in the look of the CLI login page. Every value is escaped
  by the caller or comes from the API itself."""
  template = (Path(__file__).parent / "assets" / "scm.html").read_text()
  body = template.format(title=html.escape(title), message=message, extra=extra, dot="var(--ok)" if ok else "var(--err)")
  return HTMLResponse(body, 200 if ok else 400)


def start_page(org: str, state: str, manifest_body: dict) -> HTMLResponse:
  action = f"https://github.com/organizations/{quote(org)}/settings/apps/new?state={quote(state)}"
  form = (
    f'<form id="manifest" method="post" action="{html.escape(action)}">'
    f'<input type="hidden" name="manifest" value="{html.escape(json.dumps(manifest_body))}">'
    '<button class="btn" type="submit">Continue to GitHub</button></form>'
    "<script>document.getElementById('manifest').submit()</script>"
  )
  return page("Creating the GitHub App", f"Sending the App manifest to the organization <b>{html.escape(org)}</b> …", True, form)


def router(state, journal: Journal, secrets, github: httpx.Client, public_url: str, states: States) -> APIRouter:
  routes = APIRouter(prefix="/v1/scm/connections")
  admin = require_group(ADMIN_GROUP)

  def fetch(name: str) -> dict:
    try:
      return state.get(PLURAL, name)
    except NotFound:
      raise HTTPException(404, f"connection '{name}' not found")

  def require_secrets():
    if secrets is None:
      raise HTTPException(503, "no SecretStore configured: the Platform API cannot keep credentials")

  def set_status(obj: dict, status: dict) -> dict:
    obj["status"] = {**(obj.get("status") or {}), **status}
    try:
      return state.replace_status(PLURAL, obj)
    except Conflict:
      # The controller wrote first: its status is newer than ours.
      return state.get(PLURAL, obj["metadata"]["name"])

  def replace(obj: dict, what: str) -> dict:
    try:
      return state.replace(PLURAL, obj)
    except NotFound:
      raise HTTPException(404, f"connection '{obj['metadata']['name']}' not found")
    except Conflict:
      raise HTTPException(409, f"connection '{obj['metadata']['name']}' changed while {what}: try again")

  def unset_other_defaults(but: str, actor: str) -> None:
    """At most one default: marking one unmarks the others, in the same request."""
    for obj in sorted(state.list(PLURAL), key=lambda item: item["metadata"]["name"]):
      if obj["metadata"]["name"] == but or not obj["spec"].get("default"):
        continue
      spec = {key: value for key, value in obj["spec"].items() if key != "default"}
      entry = journal.record("default", KIND, obj["metadata"]["name"], {"default": False}, actor)
      replace({**obj, "spec": spec}, "changing the default")
      journal.mark_applied(entry)

  def request_verify(obj: dict) -> dict:
    annotations = {**(obj["metadata"].get("annotations") or {}), VERIFY_ANNOTATION: format_time(datetime.now(timezone.utc))}
    obj["metadata"] = {**obj["metadata"], "annotations": annotations}
    return obj

  def record_app(name: str, app_id: int, slug: str) -> dict | None:
    """Writes the App into the spec, retrying on a fresh read: the code is already spent, so a
    conflict must not lose the App. None when the connection is gone or keeps changing."""
    for _ in range(3):
      try:
        obj = state.get(PLURAL, name)
      except NotFound:
        return None
      annotations = {**(obj["metadata"].get("annotations") or {}), APP_CREATED_ANNOTATION: "true"}
      spec = {**obj["spec"], "github": {**obj["spec"]["github"], "appId": app_id, "appSlug": slug}, "credentialRef": secret_name(name)}
      try:
        return state.replace(PLURAL, {**obj, "metadata": {**obj["metadata"], "annotations": annotations}, "spec": spec})
      except Conflict:
        continue
      except NotFound:
        return None
    return None

  def next_url(name: str, value: str) -> str:
    return f"{public_url}/v1/scm/connections/{name}/github/start?state={value}"

  @routes.post("", status_code=202)
  def create(request: ConnectionRequest, principal: Principal = Depends(admin)):
    with_key = request.appId is not None or request.privateKeyPem is not None
    if with_key and not (request.appId and request.privateKeyPem):
      raise HTTPException(422, "appId and privateKeyPem go together")
    if with_key:
      require_secrets()
    try:
      existing = state.get(PLURAL, request.name)
    except NotFound:
      existing = None
    if existing is not None:
      # An unfinished manifest flow restarts with a new state; anything else is a conflict.
      same = (existing["spec"].get("github") or {}).get("org") == request.org
      if not with_key and same and status_of(existing) == "AppNotCreated":
        return {**view(existing), "next": next_url(request.name, states.issue(request.name, principal.actor))}
      raise HTTPException(409, f"connection '{request.name}' already exists")

    spec = {"vendor": request.vendor, "github": {"org": request.org}}
    if request.default:
      spec["default"] = True
    if with_key:
      spec["github"]["appId"] = request.appId
      spec["credentialRef"] = secret_name(request.name)
    if request.default:
      unset_other_defaults(request.name, principal.actor)
    entry = journal.record("create", KIND, request.name, request.model_dump(exclude={"name"}, exclude_none=True), principal.actor)
    body = {"apiVersion": f"{GROUP}/{VERSION}", "kind": KIND, "metadata": {"name": request.name}, "spec": spec}
    if with_key:
      body = request_verify(body)
    try:
      created = state.create(PLURAL, body)
    except AlreadyExists:
      raise HTTPException(409, f"connection '{request.name}' already exists")
    # After the CR: a concurrent create of the same name must not overwrite the other one's key.
    if with_key:
      secrets.put(secret_name(request.name), {"privateKey": request.privateKeyPem}, f"{KIND}/{request.name}")
    journal.mark_applied(entry)
    if with_key:
      created = set_status(created, {"conditions": [condition("Verifying", "waiting for the controller to check the App and its installation")]})
      return view(created)
    created = set_status(created, {"conditions": [condition("AppNotCreated", "open the 'next' URL to create the GitHub App")]})
    return {**view(created), "next": next_url(request.name, states.issue(request.name, principal.actor))}

  @routes.get("")
  def list_connections(principal: Principal = Depends(admin)):
    return {"items": [view(obj) for obj in sorted(state.list(PLURAL), key=lambda obj: obj["metadata"]["name"])]}

  @routes.get("/{name}")
  def get(name: str, principal: Principal = Depends(admin)):
    return view(fetch(name))

  @routes.post("/{name}/verify", status_code=202)
  def verify(name: str, principal: Principal = Depends(admin)):
    obj = fetch(name)
    entry = journal.record("verify", KIND, name, None, principal.actor)
    updated = replace(request_verify(obj), "requesting a verification")
    journal.mark_applied(entry)
    return view(updated)

  @routes.post("/{name}/default")
  def make_default(name: str, principal: Principal = Depends(admin)):
    obj = fetch(name)
    if not obj["spec"].get("default"):
      entry = journal.record("default", KIND, name, {"default": True}, principal.actor)
      obj = replace({**obj, "spec": {**obj["spec"], "default": True}}, "changing the default")
      journal.mark_applied(entry)
    unset_other_defaults(name, principal.actor)
    return view(obj)

  @routes.delete("/{name}")
  def delete(name: str, principal: Principal = Depends(admin)):
    obj = fetch(name)
    github_spec = obj["spec"].get("github") or {}
    entry = journal.record("delete", KIND, name, None, principal.actor)
    try:
      state.delete(PLURAL, name, uid=obj["metadata"].get("uid"))
    except NotFound:
      raise HTTPException(404, f"connection '{name}' not found")
    except Conflict:
      raise HTTPException(409, f"connection '{name}' changed while deleting: try again")
    if obj["spec"].get("credentialRef") and secrets is not None:
      secrets.delete(obj["spec"]["credentialRef"])
    journal.mark_applied(entry)
    result = {"name": name, "deleted": True}
    # The App stays on GitHub: only an org owner deletes it, in the org settings. An App given with
    # --app-id was not the platform's to begin with, so there is nothing to point at.
    created = (obj["metadata"].get("annotations") or {}).get(APP_CREATED_ANNOTATION) == "true"
    if created and github_spec.get("appSlug"):
      result["appSettingsUrl"] = f"https://github.com/organizations/{github_spec['org']}/settings/apps/{github_spec['appSlug']}"
    return result

  # --- browser routes: no JWT, the state (or the controller's check) protects them ---

  def invalid_state() -> HTMLResponse:
    return page("Link expired", "This link is invalid, expired or was already used. Run <code>platform scm connection add</code> again.", False)

  @routes.get("/{name}/github/start", response_class=HTMLResponse)
  def start(name: str, state_: str = Query(alias="state")):
    if not states.peek(state_, name):
      return invalid_state()
    try:
      obj = state.get(PLURAL, name)
    except NotFound:
      return invalid_state()
    org = obj["spec"]["github"]["org"]
    return start_page(org, state_, manifest(name, org, public_url))

  @routes.get("/{name}/github/callback", response_class=HTMLResponse)
  def callback(name: str, code: str = "", state_: str = Query(default="", alias="state")):
    actor = states.consume(state_, name)
    if not actor:
      return invalid_state()
    if not CODE.fullmatch(code):
      return page("App not created", "GitHub did not send a valid code. Run <code>platform scm connection add</code> again.", False)
    require_secrets()
    try:
      obj = state.get(PLURAL, name)
    except NotFound:
      return invalid_state()
    if status_of(obj) != "AppNotCreated":
      return page("Already created", f"The connection <b>{html.escape(name)}</b> already has an App.", False)
    try:
      response = github.post(f"/app-manifests/{code}/conversions", headers={"Accept": "application/vnd.github+json"})
    except httpx.TransportError as error:
      return page("GitHub unreachable", html.escape(str(error)), False)
    if response.status_code != 201:
      return page("App not created", f"GitHub answered {response.status_code} to the manifest conversion. Run <code>platform scm connection add</code> again.", False)
    app = response.json()
    slug, app_id = str(app.get("slug", "")), app.get("id")
    if not LABEL.fullmatch(slug.lower()) or not isinstance(app_id, int):
      return page("App not created", "GitHub answered without the App id or slug.", False)
    entry = journal.record("app-created", KIND, name, {"appId": app_id, "appSlug": slug, "privateKeyPem": app.get("pem")}, actor)
    secrets.put(secret_name(name), {"privateKey": app["pem"]}, f"{KIND}/{name}")
    obj = record_app(name, app_id, slug)
    if obj is None:
      secrets.delete(secret_name(name))
      return page("App created, not recorded", f"The App {html.escape(slug)} exists, but the connection was removed or kept changing. Delete the App on GitHub and run <code>platform scm connection add</code> again.", False)
    github_spec = obj["spec"]["github"]
    journal.mark_applied(entry)
    set_status(obj, {"conditions": [condition("NotInstalled", f"install the App on the organization {github_spec['org']}: {install_url(slug)}")]})
    link = html.escape(install_url(slug))
    extra = f'<a class="btn" href="{link}">Install on {html.escape(github_spec["org"])}</a><div class="cmds">platform scm connection verify {html.escape(name)} --wait</div>'
    return page("App created", f"The GitHub App <b>{html.escape(slug)}</b> exists and its private key is stored by the platform. Now install it on the organization, on <b>all repositories</b>.", True, extra)

  @routes.get("/{name}/github/installed", response_class=HTMLResponse)
  def installed(name: str, installation_id: str = "", setup_action: str = ""):
    # No state here: GitHub calls this after any install or update of the App. The id is only a hint;
    # the controller accepts it only if it is an installation of this App on this org (App JWT).
    try:
      obj = state.get(PLURAL, name)
    except NotFound:
      return page("Unknown connection", f"There is no connection <b>{html.escape(name)}</b>.", False)
    github_spec = obj["spec"].get("github") or {}
    if not installation_id.isdigit() or not github_spec.get("appId") or len(installation_id) > 20:
      return page("Installation not recorded", "GitHub did not send a valid installation.", False)
    if status_of(obj) == "ready":
      # Anyone can call this route: it must not be a way to knock a working connection down.
      return page("Already verified", f"The connection <b>{html.escape(name)}</b> is ready. Run <code>platform scm connection verify</code> after changing the installation.", True)
    entry = journal.record("installed", KIND, name, {"installationId": int(installation_id), "setupAction": setup_action[:20]}, "github-setup-url")
    obj = request_verify({**obj, "spec": {**obj["spec"], "github": {**github_spec, "installationId": int(installation_id)}}})
    try:
      state.replace(PLURAL, obj)
    except (Conflict, NotFound):
      return page("Installation not recorded", "The connection changed meanwhile. Run <code>platform scm connection verify</code>.", False)
    journal.mark_applied(entry)
    return page("App installed", "The platform is checking the installation.", True, f'<div class="cmds">platform scm connection verify {html.escape(name)} --wait</div>')

  return routes
