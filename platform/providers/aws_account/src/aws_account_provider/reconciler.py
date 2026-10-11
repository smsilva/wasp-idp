"""Trust check of each CloudAccount (ADR 0029).

1. AssumeRole with the ExternalId must work: AccessDenied means the owner has not applied the trust policy.
2. The assumed identity must be in the account of the roleArn.
3. AssumeRole without the ExternalId must fail: a trust policy without the sts:ExternalId condition
   accepts any ExternalId, and then the handshake proves nothing.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

from botocore.exceptions import BotoCoreError, ClientError

GROUP = "platform.wasp.silvios.me"
VERIFY_ANNOTATION = f"{GROUP}/verify-requested-at"
ROLE_ACCOUNT = re.compile(r"arn:aws[-a-z]*:iam::(\d{12}):role/")
DENIED = {"AccessDenied", "AccessDeniedException"}
REVALIDATE = timedelta(hours=6)
# TrustNotEstablished is the normal state until the owner applies the policy: retry, slower each time.
BACKOFF_FIRST, BACKOFF_MAX = 30, 900

log = logging.getLogger("aws-account-provider")


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


def format_time(value: datetime) -> str:
  return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str) -> datetime:
  return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ready_condition(status: str, reason: str, message: str, now: datetime) -> dict:
  return {"type": "Ready", "status": status, "reason": reason, "message": message, "lastTransitionTime": format_time(now)}


def current_ready(obj: dict) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == "Ready"), None)


def error_code(error: Exception) -> str:
  if isinstance(error, ClientError):
    return error.response.get("Error", {}).get("Code", "")
  return ""


def summary(error: Exception) -> str:
  """What the status may show: the error code only. AWS messages name the base identity and other
  accounts, and the status is read by whoever registered the role, which may not be theirs."""
  return error_code(error) or type(error).__name__


class Reconciler:
  def __init__(self, store, sts, now=utcnow, revalidate: timedelta = REVALIDATE):
    self.store = store
    self.sts = sts
    self.now = now
    self.revalidate = revalidate
    self.retry: dict[str, tuple[datetime, int]] = {}  # uid -> (next attempt, last delay in seconds)

  def due(self, obj: dict) -> bool:
    metadata = obj["metadata"]
    status = obj.get("status") or {}
    requested = (metadata.get("annotations") or {}).get(VERIFY_ANNOTATION)
    if requested and requested != status.get("observedVerifyRequest"):
      return True
    ready = current_ready(obj)
    if ready and ready.get("status") == "True":
      validated = status.get("lastValidated")
      return not validated or self.now() - parse_time(validated) >= self.revalidate
    pending = self.retry.get(metadata.get("uid"))
    return pending is None or self.now() >= pending[0]

  def reconcile(self, obj: dict) -> None:
    metadata = obj["metadata"]
    if metadata.get("deletionTimestamp"):
      self.retry.pop(metadata.get("uid"), None)
      return
    if not self.due(obj):
      return
    status = self.validate(obj)
    requested = (metadata.get("annotations") or {}).get(VERIFY_ANNOTATION)
    if requested:
      status["observedVerifyRequest"] = requested
    self.store.patch_status(metadata["name"], status)
    reason = status["conditions"][0]["reason"]
    log.info("cloud account %s: %s", metadata["name"], reason)
    if reason == "Verified":
      self.retry.pop(metadata.get("uid"), None)
    else:
      previous = self.retry.get(metadata.get("uid"), (None, 0))[1]
      delay = min(BACKOFF_MAX, previous * 2 or BACKOFF_FIRST)
      self.retry[metadata.get("uid")] = (self.now() + timedelta(seconds=delay), delay)

  def validate(self, obj: dict) -> dict:
    name = obj["metadata"]["name"]
    aws = (obj.get("spec") or {}).get("aws") or {}
    role_arn, external_id = aws.get("roleArn", ""), aws.get("externalId")
    match = ROLE_ACCOUNT.match(role_arn)
    expected = match.group(1) if match else None
    now = self.now()
    # None removes the field in the merge patch: a failed check must not keep a previous caller.
    status = {"accountId": expected, "callerArn": None, "lastValidated": format_time(now)}

    def failed(reason: str, message: str) -> dict:
      return {**status, "conditions": [ready_condition("False", reason, message, now)]}

    session = f"platform-verify-{name}"
    try:
      credentials = self.sts.assume_role(role_arn, session, external_id)
    except ClientError as error:
      if error_code(error) in DENIED:
        return failed("TrustNotEstablished", f"the role does not trust the platform with this ExternalId yet: apply the trust policy from 'platform cloud account get {name}'")
      log.warning("cloud account %s: AssumeRole: %s", name, error)
      return failed("VerificationFailed", f"AssumeRole failed: {summary(error)}")
    except BotoCoreError as error:
      log.warning("cloud account %s: AssumeRole: %s", name, error)
      return failed("VerificationFailed", f"AssumeRole failed: {summary(error)}")

    try:
      caller = self.sts.caller_identity(credentials)
    except (ClientError, BotoCoreError) as error:
      log.warning("cloud account %s: GetCallerIdentity: %s", name, error)
      return failed("VerificationFailed", f"GetCallerIdentity failed: {summary(error)}")
    if caller["Account"] != expected:
      log.warning("cloud account %s: assumed role is in account %s, not %s", name, caller["Account"], expected)
      return failed("AccountMismatch", f"the assumed role is not in account {expected}")

    try:
      self.sts.assume_role(role_arn, f"{session}-no-external-id")
    except ClientError as error:
      if error_code(error) not in DENIED:
        log.warning("cloud account %s: AssumeRole without ExternalId: %s", name, error)
        return failed("VerificationFailed", f"AssumeRole without ExternalId failed: {summary(error)}")
    except BotoCoreError as error:
      log.warning("cloud account %s: AssumeRole without ExternalId: %s", name, error)
      return failed("VerificationFailed", f"AssumeRole without ExternalId failed: {summary(error)}")
    else:
      return failed("ExternalIdNotEnforced", "the role trusts the platform without requiring the ExternalId: add the sts:ExternalId condition of the trust policy")

    return {
      **status,
      "accountId": caller["Account"],
      "callerArn": caller["Arn"],
      "conditions": [ready_condition("True", "Verified", f"the platform assumes {role_arn} with the ExternalId, and only with it", now)],
    }
