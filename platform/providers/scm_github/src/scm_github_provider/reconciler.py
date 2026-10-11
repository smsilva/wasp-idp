import logging
import time
from datetime import datetime, timedelta, timezone

from .github import GitHubApp, GitHubError

GROUP = "platform.wasp.silvios.me"
VERIFY_ANNOTATION = f"{GROUP}/verify-requested-at"
# Must match PERMISSIONS in platform/api/src/platform_api/scm.py: the manifest asks for these.
REQUIRED = {
  "administration": "write",
  "contents": "write",
  "workflows": "write",
  "pull_requests": "write",
  "actions": "write",
  "metadata": "read",
}
LEVELS = {"read": 1, "write": 2, "admin": 3}
REVALIDATE = timedelta(hours=6)
BACKOFF_START, BACKOFF_MAX = 30, 600

log = logging.getLogger("scm-github-provider")


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


def format_time(moment: datetime) -> str:
  return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str) -> datetime:
  return datetime.fromisoformat(value.replace("Z", "+00:00"))


def condition(ready: bool, reason: str, message: str, now: datetime) -> dict:
  return {"type": "Ready", "status": "True" if ready else "False", "reason": reason, "message": message, "lastTransitionTime": format_time(now)}


def current_ready(obj: dict) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), None)


def missing_permissions(granted: dict) -> list[str]:
  return sorted(
    f"{name}:{level}" for name, level in REQUIRED.items()
    if LEVELS.get(granted.get(name, ""), 0) < LEVELS[level]
  )


class Outcome(Exception):
  """A validation that stops before Verified, with the reason of the condition."""

  def __init__(self, reason: str, message: str, observed: dict | None = None):
    super().__init__(message)
    self.reason = reason
    # What the installation has, so the status shows it even when it falls short.
    self.observed = observed or {}


class Reconciler:
  """Checks each GitHub ScmConnection that has a key: App, installation on the org, all repositories,
  permissions, and a working installation token. The result is the Ready condition (ADR 0025)."""

  def __init__(self, store, secrets, github_factory=GitHubApp, now=utcnow, clock=time.monotonic):
    self.store = store
    self.secrets = secrets
    self.github_factory = github_factory
    self.now = now
    self.clock = clock
    # name -> (seconds of the next wait, monotonic time of the next try), while not Ready.
    self.backoff: dict[str, tuple[int, float]] = {}

  def due(self, obj: dict) -> bool:
    spec = obj.get("spec") or {}
    if spec.get("vendor") != "github" or not spec.get("credentialRef") or obj["metadata"].get("deletionTimestamp"):
      return False
    status = obj.get("status") or {}
    requested = (obj["metadata"].get("annotations") or {}).get(VERIFY_ANNOTATION)
    if requested and requested != status.get("observedVerifyRequest"):
      return True
    ready = current_ready(obj)
    if ready and ready.get("status") == "True":
      last = status.get("lastValidated")
      return not last or self.now() - parse_time(last) >= REVALIDATE
    waiting = self.backoff.get(obj["metadata"]["name"])
    return waiting is None or self.clock() >= waiting[1]

  def reconcile(self, obj: dict) -> None:
    if not self.due(obj):
      return
    name = obj["metadata"]["name"]
    requested = (obj["metadata"].get("annotations") or {}).get(VERIFY_ANNOTATION)
    now = self.now()
    status = {"observedVerifyRequest": requested} if requested else {}
    try:
      status.update(self._validate(obj))
      status["conditions"] = [condition(True, "Verified", "the App is installed on every repository of the org with the permissions it needs", now)]
      self.backoff.pop(name, None)
      log.info("connection %s verified", name)
    except Outcome as outcome:
      status.update(outcome.observed)
      status["conditions"] = [condition(False, outcome.reason, str(outcome)[:500], now)]
      self._back_off(name)
      log.info("connection %s: %s", name, outcome.reason)
    except Exception as error:  # GitHub down, Secret unreadable: keep the loop alive, say why
      log.exception("verifying connection %s failed", name)
      status["conditions"] = [condition(False, "VerificationFailed", str(error)[:500], now)]
      self._back_off(name)
    status["lastValidated"] = format_time(now)
    self.store.patch_status(name, status)

  def _back_off(self, name: str) -> None:
    previous = self.backoff.get(name, (BACKOFF_START // 2, 0))[0]
    wait = min(previous * 2, BACKOFF_MAX)
    self.backoff[name] = (wait, self.clock() + wait)

  def _validate(self, obj: dict) -> dict:
    name = obj["metadata"]["name"]
    spec = obj["spec"]
    github = spec.get("github") or {}
    org = github["org"]
    key = self.secrets.private_key(spec["credentialRef"])
    if not key:
      raise Outcome("CredentialMissing", f"Secret {spec['credentialRef']} has no privateKey")
    if not github.get("appId"):
      raise Outcome("AppNotCreated", "the connection has no App id yet")
    try:
      app = self.github_factory(github["appId"], key)
      slug = app.app()["slug"]
    except GitHubError as error:
      if error.status == 401:
        raise Outcome("InvalidCredentials", f"the private key does not belong to App {github['appId']}")
      raise
    if github.get("appSlug") != slug:
      self.store.patch_spec(name, {"github": {"appSlug": slug}})

    install_url = f"https://github.com/apps/{slug}/installations/new"
    installations = app.installations()
    installation = next((item for item in installations if (item.get("account") or {}).get("login", "").lower() == org.lower()), None)
    if installation is None:
      raise Outcome("NotInstalled", f"the App {slug} is not installed on {org}: {install_url}")
    recorded = github.get("installationId")
    others = {item["id"] for item in installations if item is not installation}
    if recorded in others:
      raise Outcome("NotInstalled", f"installation {recorded} recorded for {org} belongs to another account of the App ({org}'s is {installation['id']}): reinstall from {install_url}")
    # Empty, or a hint that is no installation of this App (forged through the setup_url route, or
    # gone after a reinstall): what GitHub reports for the org wins.
    if recorded != installation["id"]:
      self.store.patch_spec(name, {"github": {"installationId": installation["id"]}})

    observed = {"permissions": installation.get("permissions") or {}, "repositorySelection": installation.get("repository_selection")}
    if installation.get("repository_selection") != "all":
      raise Outcome("NotAllRepositories", f"the App is installed on selected repositories only: grant it all repositories of {org}", observed)
    missing = missing_permissions(observed["permissions"])
    if missing:
      raise Outcome("MissingPermissions", f"the installation lacks {', '.join(missing)}: update the App permissions and accept them on {org}", observed)
    app.access_token(installation["id"])
    return observed
