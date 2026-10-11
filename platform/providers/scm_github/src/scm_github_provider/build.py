"""Runs each Build (#206): dispatches the repo's platform-build workflow, follows the run, reads its
artifact, validates the app-spec.yaml of the commit (Score) and registers the version in the index.

Dispatched → Running → Succeeded → SpecValidated, then Ready with the version in the index. The CI
runs on the repo's GitHub Actions and holds no platform credential: the platform dispatches, then pulls
the run and the artifact as the App installation, which only this provider can be (ADR 0025).

A transient failure (rate limit, GitHub or the cluster unavailable) is tried again with backoff; a
definitive one (FINAL) stops. A build Ready or stopped for 24 h is removed; the version index stays.
"""
import io
import json
import logging
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone

import httpx
from wasp_score import APP_SPEC, RESOURCE_TYPES, check, load

from .github import GitHubApp, GitHubError
from .reconciler import BACKOFF_MAX, BACKOFF_START, format_time, parse_time
from .store import CATALOG_GROUP, GROUP, VERSION, AlreadyExists

STEPS = ("Dispatched", "Running", "Succeeded", "SpecValidated")
# Ready=False with these reasons does not heal by trying again: the build stops until it is removed.
FINAL = {
  "WorkflowNotFound", "BranchNotFound", "BuildFailed", "ContractViolation", "InvalidSpec", "VersionConflict", "GitHubRejected",
}
# While the run is queued or in progress: Ready=False with this reason, and the next pass looks again.
BUILDING = "Building"
RETENTION = timedelta(hours=24)
# The contract (#206): the file name the platform dispatches, the run-name it finds the run by, the artifact.
WORKFLOW = "platform-build.yaml"
RUN_NAME = "platform-build {request_id}"
ARTIFACT = "platform-build"
RESULT_FILE = "platform-build.json"
ARTIFACT_LIMIT = 1024 * 1024
RESULT_LIMIT = 64 * 1024
# A dispatched run that does not show up by its run-name in this long breaks the contract.
RUN_LOOKUP = timedelta(minutes=10)
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?")
COMMIT = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
# A version object is named <component>.<version>: a valid DNS-1123 subdomain for every semver
# version with a well-formed pre-release.
SUBDOMAIN = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*")
COMPONENT_LABEL = f"{GROUP}/component"
# An installation token lasts one hour: reused for 50 minutes instead of one per pass.
TOKEN_REUSE = 50 * 60

log = logging.getLogger("scm-github-provider")


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


class Outcome(Exception):
  """A step that cannot go on: its condition and Ready become False with this reason."""

  def __init__(self, reason: str, message: str, errors: list[dict] | None = None):
    super().__init__(message)
    self.reason = reason
    self.errors = errors


class Waiting(Exception):
  """The run is not over yet: Ready=False with reason Building, and the next pass looks again."""


def version_name(component: str, version: str) -> str:
  return f"{component}.{version}".lower()


def read_result(archive: bytes) -> dict:
  try:
    with zipfile.ZipFile(io.BytesIO(archive)) as files, files.open(RESULT_FILE) as result:
      # Read with a bound, never by the size the zip declares: a small artifact may inflate to gigabytes.
      content = result.read(RESULT_LIMIT + 1)
    if len(content) > RESULT_LIMIT:
      raise Outcome("ContractViolation", f"{RESULT_FILE} in the {ARTIFACT} artifact is larger than {RESULT_LIMIT} bytes")
    return json.loads(content)
  except KeyError:
    raise Outcome("ContractViolation", f"the {ARTIFACT} artifact has no {RESULT_FILE}")
  except (zipfile.BadZipFile, ValueError) as error:
    raise Outcome("ContractViolation", f"{RESULT_FILE} in the {ARTIFACT} artifact is not valid JSON: {error}")


def check_result(result: dict, spec: dict, component: str) -> dict:
  """The fields of platform-build.json, as the contract defines them."""
  if not isinstance(result, dict):
    raise Outcome("ContractViolation", f"{RESULT_FILE} is not a JSON object")
  errors = []
  for field in ("version", "image", "digest", "commit", "branch", "requestId"):
    if not isinstance(result.get(field), str) or not result[field]:
      errors.append(f"{field} is missing")
  if errors:
    raise Outcome("ContractViolation", f"{RESULT_FILE}: {'; '.join(errors)}")
  if not VERSION_PATTERN.fullmatch(result["version"]):
    errors.append(f"version '{result['version']}' is not <major>.<minor>.<patch>[-<pre-release>]")
  elif not SUBDOMAIN.fullmatch(version_name(component, result["version"])) or len(version_name(component, result["version"])) > 253:
    errors.append(f"version '{result['version']}' cannot name the version object '{version_name(component, result['version'])}' (an empty pre-release identifier, or too long)")
  if spec.get("version") and result["version"] != spec["version"]:
    errors.append(f"version is '{result['version']}', the build asked for '{spec['version']}'")
  if not COMMIT.fullmatch(result["commit"]):
    errors.append(f"commit '{result['commit']}' is not a full sha")
  if not DIGEST.fullmatch(result["digest"]):
    errors.append(f"digest '{result['digest']}' is not sha256:<hex>")
  if result["requestId"] != spec["requestId"]:
    errors.append(f"requestId '{result['requestId']}' is not this build's")
  if result["branch"] != spec["branch"]:
    errors.append(f"branch '{result['branch']}' is not '{spec['branch']}'")
  if errors:
    raise Outcome("ContractViolation", f"{RESULT_FILE}: {'; '.join(errors)}")
  return {field: result[field] for field in ("version", "image", "digest", "commit", "branch", "requestId")}


class BuildReconciler:
  def __init__(self, builds, connections, versions, resources, secrets, github_factory=GitHubApp, now=utcnow, clock=time.monotonic, resource_types=RESOURCE_TYPES):
    self.builds = builds
    self.connections = connections
    self.versions = versions
    self.resources = resources
    self.secrets = secrets
    self.github_factory = github_factory
    self.now = now
    self.clock = clock
    self.resource_types = tuple(resource_types)
    # name -> (seconds of the next wait, monotonic time of the next try), while a build fails.
    self.backoff: dict[str, tuple[float, float]] = {}
    # connection name -> (installation client, monotonic time it stops being reused).
    self.installations: dict[str, tuple[object, float]] = {}

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
    failed = True
    try:
      installation = self._installation(obj)
      self._dispatched(obj, installation, work)
      self._running(obj, installation, work)
      self._succeeded(obj, installation, work)
      document = self._spec_validated(obj, installation, work)
      self._registered(obj, installation, work, document)
      failed = False
    except Waiting as waiting_for:
      self._set(work, "Ready", False, BUILDING, str(waiting_for))
      failed = False
    except Outcome as outcome:
      if outcome.errors is not None:
        work["errors"] = outcome.errors
      self._fail(work, outcome.reason, str(outcome))
      log.info("build %s: %s", name, outcome.reason)
    except GitHubError as error:
      if error.transient:
        reason = "RateLimited" if error.rate_limited else "GitHubUnavailable"
        retry_after = error.retry_after
      else:  # a 4xx GitHub will keep answering: say why and stop
        reason = "GitHubRejected"
      log.warning("build %s: %s", name, error)
      self._fail(work, reason, str(error))
    except httpx.TransportError as error:
      log.warning("build %s: GitHub unreachable: %s", name, error)
      self._fail(work, "GitHubUnavailable", f"GitHub unreachable: {error}")
    except Exception as error:  # the cluster unavailable, or a bug: say why, try again later
      log.exception("build %s failed", name)
      self._fail(work, "StepFailed", str(error))
    ready = work["conditions"]["Ready"]
    if not failed or ready["reason"] in FINAL:
      self.backoff.pop(name, None)
    else:
      self._back_off(name, retry_after)
    self._save(name, status, work)

  def _back_off(self, name: str, retry_after: float | None) -> None:
    previous = self.backoff.get(name, (BACKOFF_START / 2, 0))[0]
    wait = min(previous * 2, BACKOFF_MAX)
    self.backoff[name] = (wait, self.clock() + max(wait, retry_after or 0))

  def _expire(self, name: str, ready: dict) -> None:
    since = ready.get("lastTransitionTime")
    if since and self.now() - parse_time(since) >= RETENTION:
      self.builds.delete(name)
      log.info("build %s removed after %s (%s)", name, RETENTION, ready.get("reason"))

  def _installation(self, obj: dict):
    """The connection may have changed since the API accepted the request."""
    name = obj["spec"]["scmConnection"]
    connection = self.connections.get(name)
    if connection is None:
      raise Outcome("ConnectionNotFound", f"scm connection '{name}' not found")
    ready = next((c for c in (connection.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), {})
    spec = connection["spec"]
    github = spec.get("github") or {}
    if ready.get("status") != "True" or not github.get("installationId") or not spec.get("credentialRef"):
      raise Outcome("ConnectionNotReady", f"scm connection '{name}' is not ready ({ready.get('reason', 'pending')})")
    cached = self.installations.get(name)
    if cached is not None and self.clock() < cached[1]:
      return cached[0]
    key = self.secrets.private_key(spec["credentialRef"])
    if not key:
      raise Outcome("CredentialMissing", f"Secret {spec['credentialRef']} has no privateKey")
    installation = self.github_factory(github["appId"], key).installation(github["installationId"])
    self.installations[name] = (installation, self.clock() + TOKEN_REUSE)
    return installation

  # --- steps ---

  def _find_run(self, obj: dict, installation) -> dict | None:
    spec = obj["spec"]
    title = RUN_NAME.format(request_id=spec["requestId"])
    runs = [run for run in installation.dispatched_runs(spec["repo"], spec["branch"]) if run.get("display_title") == title]
    # Two runs with the same request id only after a dispatch repeated by a restart: the first one counts.
    return min(runs, key=lambda run: run["id"]) if runs else None

  def _dispatched(self, obj: dict, installation, work: dict) -> None:
    if self._done(work, "Dispatched"):
      return
    spec = obj["spec"]
    repo = spec["repo"]
    if installation.workflow(repo, WORKFLOW) is None:
      raise Outcome("WorkflowNotFound", f"{repo} has no .github/workflows/{WORKFLOW} on its default branch: the build contract asks for it (workflow_dispatch with request-id and version)")
    if not installation.branch_exists(repo, spec["branch"]):
      raise Outcome("BranchNotFound", f"branch '{spec['branch']}' not found in {repo}")
    # A restart after the dispatch and before the status was saved: the run is there, do not dispatch again.
    if self._find_run(obj, installation) is None:
      inputs = {"request-id": spec["requestId"]}
      if spec.get("version"):
        inputs["version"] = spec["version"]
      try:
        installation.dispatch(repo, WORKFLOW, spec["branch"], inputs)
      except GitHubError as error:
        if error.status == 422:  # no workflow_dispatch trigger, or inputs the workflow does not declare
          raise Outcome("ContractViolation", f"{WORKFLOW} refused the dispatch: {error}")
        raise
    self._set(work, "Dispatched", True, "Dispatched", f"{WORKFLOW} dispatched on {spec['branch']}")
    # Saved at once: a restart must not dispatch twice.
    self.builds.patch_status(obj["metadata"]["name"], self._status(work))

  def _running(self, obj: dict, installation, work: dict) -> None:
    if self._done(work, "Succeeded"):
      return
    run = self._find_run(obj, installation)
    if run is None:
      since = parse_time(work["conditions"]["Dispatched"]["lastTransitionTime"])
      title = RUN_NAME.format(request_id=obj["spec"]["requestId"])
      if self.now() - since >= RUN_LOOKUP:
        raise Outcome("ContractViolation", f"no run named '{title}' {RUN_LOOKUP} after the dispatch: {WORKFLOW} must set run-name: platform-build ${{{{ inputs.request-id }}}}")
      self._set(work, "Running", False, "Queued", f"waiting for the run '{title}'")
      raise Waiting(f"waiting for the run '{title}'")
    work["runUrl"] = run["html_url"]
    work["run"] = {"id": run["id"], "headSha": run.get("head_sha")}
    self._set(work, "Running", True, "Started", run["html_url"])
    if run.get("status") != "completed":
      raise Waiting(f"run {run['status']}: {run['html_url']}")
    if run.get("conclusion") != "success":
      raise Outcome("BuildFailed", f"the run ended {run.get('conclusion')}: {run['html_url']}")

  def _succeeded(self, obj: dict, installation, work: dict) -> None:
    if self._done(work, "Succeeded"):
      return
    spec = obj["spec"]
    artifact = next((item for item in installation.run_artifacts(spec["repo"], work["run"]["id"]) if item.get("name") == ARTIFACT and not item.get("expired")), None)
    if artifact is None:
      raise Outcome("ContractViolation", f"the run has no {ARTIFACT} artifact: {work['runUrl']}")
    try:
      archive = installation.download_artifact(spec["repo"], artifact["id"], ARTIFACT_LIMIT)
    except ValueError as error:
      raise Outcome("ContractViolation", str(error))
    work["result"] = check_result(read_result(archive), spec, spec["component"])
    self._set(work, "Succeeded", True, "Built", f"image {work['result']['image']}:{work['result']['version']} pushed")

  def _app_spec(self, obj: dict, installation, commit: str) -> str:
    text = installation.file_at(obj["spec"]["repo"], APP_SPEC, commit)
    if text is None:
      raise Outcome("InvalidSpec", f"{APP_SPEC} not found at {commit[:7]}", [{"field": APP_SPEC, "reason": "not found"}])
    return text.decode("utf-8", errors="replace")

  def _spec_validated(self, obj: dict, installation, work: dict) -> dict | None:
    """A version without a valid spec does not exist for the platform: the image stays in the
    registry, the version is not registered. Returns the validated document, None when an earlier
    pass validated it."""
    if self._done(work, "SpecValidated"):
      return None
    commit = work["result"]["commit"]
    result = check(self._app_spec(obj, installation, commit), self._resource_exists, self.resource_types)
    work["appSpec"] = {"resources": result.resources}
    if not result.valid:
      raise Outcome("InvalidSpec", f"{APP_SPEC} at {commit[:7]}: {len(result.errors)} error(s)", result.errors)
    self._set(work, "SpecValidated", True, "Valid", f"{APP_SPEC} valid at {commit[:7]}")
    return result.document

  def _resource_exists(self, name: str) -> bool:
    return self.resources.get(name) is not None

  def _registered(self, obj: dict, installation, work: dict, document: dict | None) -> None:
    spec = obj["spec"]
    result = work["result"]
    if document is None:
      # Validated in an earlier pass (a restart, or a failure after it): read again at the same commit.
      document = load(self._app_spec(obj, installation, result["commit"]))
    name = version_name(spec["component"], result["version"])
    body = {
      "apiVersion": f"{CATALOG_GROUP}/{VERSION}",
      "kind": "Version",
      "metadata": {"name": name, "labels": {COMPONENT_LABEL: spec["component"]}},
      "spec": {
        "component": spec["component"],
        "version": result["version"],
        "image": result["image"],
        "digest": result["digest"],
        "commit": result["commit"],
        "branch": result["branch"],
        "createdAt": format_time(self.now()),
        "build": obj["metadata"]["name"],
        # The Workload Spec (ADR 0033): what a deploy of this version renders, without GitHub.
        "appSpec": document,
      },
    }
    try:
      self.versions.create(body)
    except AlreadyExists:
      current = (self.versions.get(name) or {}).get("spec") or {}
      # The same commit built again under the same version is the same version: nothing to change.
      if current.get("version") != result["version"] or current.get("commit") != result["commit"]:
        raise Outcome("VersionConflict", f"{spec['component']} {current.get('version')} is already in the index from commit {str(current.get('commit'))[:7]}: it is left untouched")
    self._set(work, "Ready", True, "Registered", f"{spec['component']} {result['version']} in the version index")
    log.info("build %s ready: %s %s", obj["metadata"]["name"], spec["component"], result["version"])

  # --- status ---

  def _set(self, work: dict, type_: str, ok: bool, reason: str, message: str) -> None:
    previous = work["conditions"].get(type_)
    status = "True" if ok else "False"
    same = previous and previous.get("status") == status and previous.get("reason") == reason
    moment = previous["lastTransitionTime"] if same and previous.get("lastTransitionTime") else format_time(self.now())
    work["conditions"][type_] = {"type": type_, "status": status, "reason": reason, "message": message[:500], "lastTransitionTime": moment}

  def _fail(self, work: dict, reason: str, message: str) -> None:
    # The first step not done yet carries the failure, and Ready repeats it.
    step = next((item for item in STEPS if not self._done(work, item)), STEPS[-1])
    self._set(work, step, False, reason, message)
    self._set(work, "Ready", False, reason, message)

  @staticmethod
  def _done(work: dict, step: str) -> bool:
    return work["conditions"].get(step, {}).get("status") == "True"

  def _status(self, work: dict) -> dict:
    status = {key: value for key, value in work.items() if key != "conditions"}
    order = [*STEPS, "Ready"]
    status["conditions"] = sorted(work["conditions"].values(), key=lambda item: order.index(item["type"]) if item["type"] in order else len(order))
    return status

  def _save(self, name: str, before: dict, work: dict) -> None:
    # Only a change is written: an unchanged status would otherwise wake the watch again at once.
    status = self._status(work)
    if status != {**before, "conditions": before.get("conditions", [])}:
      self.builds.patch_status(name, status)
