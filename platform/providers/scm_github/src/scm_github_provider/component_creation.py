"""Runs each ComponentCreation (#204): one idempotent step per condition, resumable after a restart.

Validated → Rendered → RepoCreated → Pushed → Protected → Registered, then Ready. This provider is the
only one that reads the App key (ADR 0025), so the repo is created here, as the installation on the org.

A transient failure (rate limit, GitHub or the cluster unavailable) is tried again with backoff; a
definitive one (FINAL) stops. A creation Ready or stopped for 24 h is removed; the component index stays.
"""
import logging
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml
from wasp_templates.render import CATALOG_INFO, annotate_origin, render
from wasp_templates.source import fetch

from .github import GitHubApp, GitHubError
from .reconciler import BACKOFF_MAX, BACKOFF_START, format_time, parse_time
from .store import CATALOG_GROUP, VERSION, AlreadyExists

# STEPS, FINAL and RETENTION have a copy in platform/api/src/platform_api/components.py (a separate uv
# project, which frees a stopped creation's name): a test fails when they differ.
STEPS = ("Validated", "Rendered", "RepoCreated", "Pushed", "Protected", "Registered")
# Protected=False with this reason is a warning, not a failure: Ready does not wait for it.
UNPROTECTED = "ProtectionUnavailable"
# Ready=False with these reasons does not heal by trying again: the creation stops until it is removed.
FINAL = {"RepoAlreadyExists", "RepoGone", "ComponentExists", "GitHubRejected"}
# Ready, or stopped on a FINAL reason, for this long: the creation is removed and its name is free again.
RETENTION = timedelta(hours=24)
BRANCH = "main"
# In every first commit: how Pushed recognises its own commit after a restart.
TRAILER = "Platform-Component-Creation"
PROJECT_SLUG = "github.com/project-slug"
PRD = "docs/prd.md"
APP_SPEC = "app-spec.yaml"

log = logging.getLogger("scm-github-provider")


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


class Outcome(Exception):
  """A step that cannot go on: its condition and Ready become False with this reason."""

  def __init__(self, reason: str, message: str):
    super().__init__(message)
    self.reason = reason


def summarize_app_spec(text: str) -> dict:
  """What the Score file declares, for the `component create --wait` summary."""
  try:
    document = yaml.safe_load(text) or {}
  except yaml.YAMLError:
    return {}
  if not isinstance(document, dict):
    return {}
  resources = document.get("resources") or {}
  routes = [
    str((item.get("params") or {}).get("path"))
    for item in resources.values()
    if isinstance(item, dict) and item.get("type") == "route" and (item.get("params") or {}).get("path")
  ]
  return {
    "containers": sorted(document.get("containers") or {}),
    "resources": sorted({item["type"] for item in resources.values() if isinstance(item, dict) and item.get("type") not in (None, "route", "dns")}),
    "routes": routes,
  }


def first_component(path: Path) -> tuple[list, dict | None]:
  documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
  return documents, next((doc for doc in documents if isinstance(doc, dict) and doc.get("kind") == "Component"), None)


class CreationReconciler:
  def __init__(self, creations, connections, components, secrets, workdir: Path, github_factory=GitHubApp, fetch_source=fetch, now=utcnow, clock=time.monotonic):
    self.creations = creations
    self.connections = connections
    self.components = components
    self.secrets = secrets
    self.workdir = workdir
    self.github_factory = github_factory
    self.fetch_source = fetch_source
    self.now = now
    self.clock = clock
    # name -> (seconds of the next wait, monotonic time of the next try), while a creation fails.
    self.backoff: dict[str, tuple[float, float]] = {}

  def reconcile(self, obj: dict) -> None:
    if obj["metadata"].get("deletionTimestamp"):
      return
    name = obj["metadata"]["name"]
    status = obj.get("status") or {}
    conditions = {item["type"]: item for item in status.get("conditions", [])}
    ready = conditions.get("Ready", {})
    if ready.get("status") == "True" or ready.get("reason") in FINAL:
      self.backoff.pop(name, None)
      self._expire(name, ready)
      return
    waiting = self.backoff.get(name)
    if waiting is not None and self.clock() < waiting[1]:
      return
    work = dict(status)
    work["conditions"] = conditions
    retry_after = None
    try:
      connection = self._validated(obj, work)
      output = self._rendered(obj, connection, work)
      installation = self._installation(connection)
      self._repo_created(obj, connection, installation, work)
      self._pushed(obj, installation, output, work)
      self._protected(installation, work)
      self._registered(obj, output, work)
      message = f"{work['repo']['fullName']} created and registered"
      if work["conditions"]["Protected"]["status"] != "True":
        message += f"; {BRANCH} not protected"
      self._set(work, "Ready", True, "Created", message)
      shutil.rmtree(self._folder(obj), ignore_errors=True)
      log.info("component creation %s ready", name)
    except Outcome as outcome:
      self._fail(work, outcome.reason, str(outcome))
      log.info("component creation %s: %s", name, outcome.reason)
    except GitHubError as error:
      if error.transient:
        reason = "RateLimited" if error.rate_limited else "GitHubUnavailable"
        retry_after = error.retry_after
      else:  # a 4xx GitHub will keep answering: say why and stop
        reason = "GitHubRejected"
      log.warning("component creation %s: %s", name, error)
      self._fail(work, reason, str(error))
    except httpx.TransportError as error:
      log.warning("component creation %s: GitHub unreachable: %s", name, error)
      self._fail(work, "GitHubUnavailable", f"GitHub unreachable: {error}")
    except Exception as error:  # the cluster unavailable, or a bug: say why, try again later
      log.exception("component creation %s failed", name)
      self._fail(work, "StepFailed", str(error))
    ready = work["conditions"]["Ready"]
    if ready["status"] == "True" or ready["reason"] in FINAL:
      self.backoff.pop(name, None)
    else:
      self._back_off(name, retry_after)
    self._save(name, status, work)

  def _back_off(self, name: str, retry_after: float | None) -> None:
    """Doubles from BACKOFF_START up to BACKOFF_MAX, as for the connections; a rate limit waits at
    least until GitHub's reset, even past the cap."""
    previous = self.backoff.get(name, (BACKOFF_START / 2, 0))[0]
    wait = min(previous * 2, BACKOFF_MAX)
    self.backoff[name] = (wait, self.clock() + max(wait, retry_after or 0))

  def _expire(self, name: str, ready: dict) -> None:
    since = ready.get("lastTransitionTime")
    if since and self.now() - parse_time(since) >= RETENTION:
      self.creations.delete(name)
      log.info("component creation %s removed after %s (%s)", name, RETENTION, ready.get("reason"))

  # --- steps ---

  def _validated(self, obj: dict, work: dict) -> dict:
    """The connection may have changed since the API accepted the request."""
    name = obj["spec"]["scmConnection"]
    connection = self.connections.get(name)
    if connection is None:
      raise Outcome("ConnectionNotFound", f"scm connection '{name}' not found")
    ready = next((c for c in (connection.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), {})
    github = connection["spec"].get("github") or {}
    if ready.get("status") != "True" or not github.get("installationId") or not connection["spec"].get("credentialRef"):
      raise Outcome("ConnectionNotReady", f"scm connection '{name}' is not ready ({ready.get('reason', 'pending')})")
    self._set(work, "Validated", True, "Validated", f"scm connection '{name}' is ready")
    return connection

  def _folder(self, obj: dict) -> Path:
    # By uid: a creation deleted and requested again under the same name never reuses old content.
    return self.workdir / obj["metadata"]["uid"]

  def _rendered(self, obj: dict, connection: dict, work: dict) -> Path:
    """The content lives in the controller's volume, never in the CR. Gone after a restart, it renders
    again: the ref is fixed, so the result is the same."""
    folder = self._folder(obj)
    output = folder / "output"
    done = folder / "rendered"
    if done.exists() and work["conditions"].get("Rendered", {}).get("status") == "True":
      return output
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    spec = obj["spec"]
    name = obj["metadata"]["name"]
    template = spec["template"]
    content = self.fetch_source(template["source"], folder / "fetch")
    values = {
      **(spec.get("params") or {}),
      "name": name, "owner": spec["owner"], "system": spec["system"], "description": spec.get("description") or "",
    }
    render(content, output, values, template.get("copyWithoutRendering") or [])
    shutil.rmtree(folder / "fetch", ignore_errors=True)
    annotate_origin(output, f"{template['name']}@{template['source']['ref']}")
    self._annotate_slug(output, f"{connection['spec']['github']['org']}/{name}")
    if spec.get("prd") is not None:
      (output / PRD).parent.mkdir(parents=True, exist_ok=True)
      (output / PRD).write_text(spec["prd"], encoding="utf-8")
    files = sorted(path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file())
    work["files"] = files
    if (output / APP_SPEC).is_file():
      work["appSpec"] = summarize_app_spec((output / APP_SPEC).read_text(encoding="utf-8"))
    done.touch()
    self._set(work, "Rendered", True, "Rendered", f"{len(files)} files from {template['name']}@{template['source']['ref']}")
    return output

  def _annotate_slug(self, output: Path, full_name: str) -> None:
    path = output / CATALOG_INFO
    if not path.is_file():
      return
    documents, component = first_component(path)
    if component is None:
      return
    component.setdefault("metadata", {}).setdefault("annotations", {})[PROJECT_SLUG] = full_name
    path.write_text(yaml.safe_dump_all(documents, sort_keys=False, allow_unicode=True), encoding="utf-8")

  def _installation(self, connection: dict):
    spec = connection["spec"]
    key = self.secrets.private_key(spec["credentialRef"])
    if not key:
      raise Outcome("CredentialMissing", f"Secret {spec['credentialRef']} has no privateKey")
    return self.github_factory(spec["github"]["appId"], key).installation(spec["github"]["installationId"])

  def _repo_created(self, obj: dict, connection: dict, installation, work: dict) -> None:
    name = obj["metadata"]["name"]
    org = connection["spec"]["github"]["org"]
    full_name = f"{org}/{name}"
    recorded = work.get("repo") or {}
    existing = installation.repo(full_name)
    if existing is not None:
      # Only a repo this creation made, proven by its node id, is ever touched: never adopt another.
      if not recorded.get("nodeId") or recorded["nodeId"] != existing.get("node_id"):
        raise Outcome("RepoAlreadyExists", f"{full_name} exists and was not created by this request: it is left untouched")
    else:
      if recorded.get("nodeId"):
        raise Outcome("RepoGone", f"{full_name} was created and then deleted outside the platform")
      try:
        existing = installation.create_repo(org, name, obj["spec"]["visibility"] == "private", obj["spec"].get("description"))
      except GitHubError as error:
        if error.status == 422 and "already exists" in str(error):
          raise Outcome("RepoAlreadyExists", f"{full_name} exists and was not created by this request: it is left untouched")
        raise
      work["repo"] = {"fullName": existing["full_name"], "url": existing["html_url"], "nodeId": existing["node_id"]}
      # Saved at once: a restart before the end of the pass must still know the repo is ours.
      self._set(work, "RepoCreated", True, "Created", f"{full_name} created ({obj['spec']['visibility']})")
      self.creations.patch_status(name, self._status(work))
      return
    self._set(work, "RepoCreated", True, "Created", f"{full_name} created ({obj['spec']['visibility']})")

  def _pushed(self, obj: dict, installation, output: Path, work: dict) -> None:
    name = obj["metadata"]["name"]
    full_name = work["repo"]["fullName"]
    marker = f"{TRAILER}: {name}"
    head = installation.head(full_name, BRANCH)
    if head is not None and marker in installation.commit_message(full_name, head).splitlines():
      self._set(work, "Pushed", True, "Pushed", f"first commit {head[:7]} on {BRANCH}")
      return
    entries = []
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
      entries.append({
        "path": path.relative_to(output).as_posix(),
        "mode": "100755" if path.stat().st_mode & 0o111 else "100644",
        "type": "blob",
        "sha": installation.blob(full_name, path.read_bytes()),
      })
    tree = installation.tree(full_name, entries)
    template = obj["spec"]["template"]
    message = f"Create {name} from template {template['name']}@{template['source']['ref']}\n\n{marker}\n"
    # No parent: the README commit of auto_init is replaced, the repo starts with this commit only.
    commit = installation.commit(full_name, message, tree, [])
    installation.point_branch(full_name, BRANCH, commit, exists=head is not None)
    self._set(work, "Pushed", True, "Pushed", f"first commit {commit[:7]} on {BRANCH}")

  def _protected(self, installation, work: dict) -> None:
    """main changes only by pull request. GitHub Free has no protection for private repos: a warning,
    the creation still ends Ready."""
    if work["conditions"].get("Protected", {}).get("status") == "True":
      return
    full_name = work["repo"]["fullName"]
    try:
      installation.protect(full_name, BRANCH)
    except GitHubError as error:
      if error.status != 403 or error.transient:
        raise
      self._set(work, "Protected", False, UNPROTECTED, f"{BRANCH} of {full_name} is not protected: {error}")
      return
    self._set(work, "Protected", True, "Protected", f"{BRANCH} changes only by pull request (no approval required)")

  def _registered(self, obj: dict, output: Path, work: dict) -> None:
    """The index is a read mirror of the rendered catalog-info.yaml (ADR 0023)."""
    name = obj["metadata"]["name"]
    spec = obj["spec"]
    component = {}
    if (output / CATALOG_INFO).is_file():
      component = first_component(output / CATALOG_INFO)[1] or {}
    declared = component.get("spec") or {}
    template = spec["template"]
    index_spec = {
      "owner": declared.get("owner") or spec["owner"],
      "system": declared.get("system") or spec["system"],
      "type": declared.get("type") or spec.get("type"),
      "lifecycle": "experimental",
      "source": {"repo": work["repo"]["fullName"], "template": f"{template['name']}@{template['source']['ref']}", "origin": "created"},
    }
    description = (component.get("metadata") or {}).get("description") or spec.get("description")
    if description:
      index_spec["description"] = description
    body = {"apiVersion": f"{CATALOG_GROUP}/{VERSION}", "kind": "Component", "metadata": {"name": name}, "spec": index_spec}
    try:
      self.components.create(body)
    except AlreadyExists:
      current = self.components.get(name)
      if ((current or {}).get("spec") or {}).get("source", {}).get("repo") != work["repo"]["fullName"]:
        raise Outcome("ComponentExists", f"component '{name}' is already in the index for another repo")
      self.components.replace({**body, "metadata": {"name": name, "resourceVersion": current["metadata"]["resourceVersion"]}})
    self._set(work, "Registered", True, "Registered", "in the catalog (lifecycle: experimental)")

  # --- status ---

  def _set(self, work: dict, type_: str, ok: bool, reason: str, message: str) -> None:
    previous = work["conditions"].get(type_)
    status = "True" if ok else "False"
    same = previous and previous.get("status") == status and previous.get("reason") == reason
    moment = previous["lastTransitionTime"] if same and previous.get("lastTransitionTime") else format_time(self.now())
    work["conditions"][type_] = {"type": type_, "status": status, "reason": reason, "message": message[:500], "lastTransitionTime": moment}

  def _fail(self, work: dict, reason: str, message: str) -> None:
    # The first step not done yet carries the failure, and Ready repeats it; an unprotected main is done.
    step = next((item for item in STEPS if not self._done(work, item)), STEPS[-1])
    self._set(work, step, False, reason, message)
    self._set(work, "Ready", False, reason, message)

  @staticmethod
  def _done(work: dict, step: str) -> bool:
    current = work["conditions"].get(step, {})
    return current.get("status") == "True" or current.get("reason") == UNPROTECTED

  def _status(self, work: dict) -> dict:
    status = {key: value for key, value in work.items() if key != "conditions"}
    order = [*STEPS, "Ready"]
    status["conditions"] = sorted(work["conditions"].values(), key=lambda item: order.index(item["type"]) if item["type"] in order else len(order))
    return status

  def _save(self, name: str, before: dict, work: dict) -> None:
    # Only a change is written: an unchanged failure would otherwise wake the watch again at once.
    status = self._status(work)
    if status != {**before, "conditions": before.get("conditions", [])}:
      self.creations.patch_status(name, status)
