from datetime import datetime, timedelta, timezone

import boto3
import pytest
from botocore.stub import ANY, Stubber

from aws_account_provider.main import publish_base
from aws_account_provider.reconciler import VERIFY_ANNOTATION, Reconciler, format_time
from aws_account_provider.sts import Sts

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
ROLE = "arn:aws:iam::123456789012:role/platform"
EXTERNAL_ID = "external-id-of-this-account"
CREDENTIALS = {"AccessKeyId": "ASIAEXAMPLE0000000000", "SecretAccessKey": "secret", "SessionToken": "token", "Expiration": NOW}


class FakeStore:
  def __init__(self):
    self.statuses = {}
    self.base = None

  def patch_status(self, name, status):
    self.statuses.setdefault(name, []).append(status)

  def publish_base_identity(self, arn, account):
    self.base = (arn, account)

  def clear_base_identity(self):
    self.base = None


def sts_client():
  return boto3.client("sts", region_name="us-east-1", aws_access_key_id="base", aws_secret_access_key="base")


class Aws:
  """Stubbed STS: `base` answers on the base credential, `assumed` on the assumed role."""

  def __init__(self):
    self.base_client, self.assumed_client = sts_client(), sts_client()
    self.base, self.assumed = Stubber(self.base_client), Stubber(self.assumed_client)
    self.base.activate()
    self.assumed.activate()
    self.sts = Sts(lambda credentials: self.assumed_client if credentials else self.base_client)

  def assume(self, external_id=EXTERNAL_ID, error=None):
    params = {"RoleArn": ROLE, "RoleSessionName": ANY, "DurationSeconds": 900}
    if external_id:
      params["ExternalId"] = external_id
    if error:
      self.base.add_client_error("assume_role", service_error_code=error, http_status_code=403, expected_params=params)
    else:
      self.base.add_response("assume_role", {"Credentials": CREDENTIALS}, params)

  def caller(self, account="123456789012"):
    self.assumed.add_response("get_caller_identity", {"Account": account, "Arn": f"arn:aws:sts::{account}:assumed-role/platform/platform-verify-nonprod", "UserId": "AROAEXAMPLE:platform-verify-nonprod"})


def account(**status):
  return {
    "metadata": {"name": "nonprod", "uid": "uid-1", "annotations": {}},
    "spec": {"vendor": "aws", "aws": {"roleArn": ROLE, "externalId": EXTERNAL_ID}},
    "status": status,
  }


@pytest.fixture
def aws():
  return Aws()


@pytest.fixture
def store():
  return FakeStore()


def reconcile(store, aws, obj, now=NOW):
  reconciler = Reconciler(store, aws.sts, now=lambda: now)
  reconciler.reconcile(obj)
  return reconciler


def last(store):
  status = store.statuses["nonprod"][-1]
  return status["conditions"][0]["reason"], status


def test_verified(store, aws):
  aws.assume()
  aws.caller()
  aws.assume(external_id=None, error="AccessDenied")
  reconcile(store, aws, account())
  reason, status = last(store)
  assert reason == "Verified"
  assert status["conditions"][0]["status"] == "True"
  assert status["accountId"] == "123456789012"
  assert status["callerArn"].startswith("arn:aws:sts::123456789012:assumed-role/platform/")
  assert status["lastValidated"] == "2026-10-11T12:00:00Z"
  aws.base.assert_no_pending_responses()


def test_trust_not_established(store, aws):
  aws.assume(error="AccessDenied")
  reconcile(store, aws, account())
  reason, status = last(store)
  assert reason == "TrustNotEstablished"
  assert status["accountId"] == "123456789012"
  assert status["callerArn"] is None


def test_account_mismatch(store, aws):
  aws.assume()
  aws.caller(account="210987654321")
  reconcile(store, aws, account())
  assert last(store)[0] == "AccountMismatch"


def test_external_id_not_enforced(store, aws):
  aws.assume()
  aws.caller()
  aws.assume(external_id=None)
  reconcile(store, aws, account())
  reason, status = last(store)
  assert reason == "ExternalIdNotEnforced"
  assert status["conditions"][0]["status"] == "False"


def test_other_errors_are_reported(store, aws):
  aws.assume(error="ExpiredToken")
  reconcile(store, aws, account())
  reason, status = last(store)
  assert reason == "VerificationFailed"
  assert "ExpiredToken" in status["conditions"][0]["message"]


def test_not_ready_backs_off(store, aws):
  aws.assume(error="AccessDenied")
  reconciler = reconcile(store, aws, account())
  pending = account(conditions=[{"type": "Ready", "status": "False", "reason": "TrustNotEstablished"}])
  # Our own status patch comes back as a watch event: nothing to do until the retry time.
  reconciler.reconcile(pending)
  assert len(store.statuses["nonprod"]) == 1
  reconciler.now = lambda: NOW + timedelta(seconds=30)
  aws.assume(error="AccessDenied")
  reconciler.reconcile(pending)
  assert len(store.statuses["nonprod"]) == 2
  assert reconciler.retry["uid-1"][1] == 60


def test_verify_request_runs_now_and_is_echoed(store, aws):
  ready = account(lastValidated=format_time(NOW), conditions=[{"type": "Ready", "status": "True", "reason": "Verified"}])
  reconciler = Reconciler(store, aws.sts, now=lambda: NOW)
  assert not reconciler.due(ready)
  ready["metadata"]["annotations"][VERIFY_ANNOTATION] = "2026-10-11T12:00:00Z"
  assert reconciler.due(ready)
  aws.assume(error="AccessDenied")
  reconciler.reconcile(ready)
  assert last(store)[1]["observedVerifyRequest"] == "2026-10-11T12:00:00Z"
  ready["status"]["observedVerifyRequest"] = "2026-10-11T12:00:00Z"
  ready["status"]["conditions"][0]["status"] = "True"
  assert not reconciler.due(ready)


def test_ready_revalidates_after_six_hours(store, aws):
  ready = account(lastValidated=format_time(NOW), conditions=[{"type": "Ready", "status": "True", "reason": "Verified"}])
  reconciler = Reconciler(store, aws.sts, now=lambda: NOW + timedelta(hours=5))
  assert not reconciler.due(ready)
  reconciler.now = lambda: NOW + timedelta(hours=6)
  assert reconciler.due(ready)


def test_deleted_accounts_are_skipped(store, aws):
  obj = account()
  obj["metadata"]["deletionTimestamp"] = "2026-10-11T12:00:00Z"
  reconcile(store, aws, obj)
  assert store.statuses == {}


def test_base_identity_is_published_and_cleared(store, aws):
  aws.base.add_response("get_caller_identity", {"Account": "210987654321", "Arn": "arn:aws:iam::210987654321:user/platform-base", "UserId": "AIDAEXAMPLE"})
  assert publish_base(store, aws.sts)
  assert store.base == ("arn:aws:iam::210987654321:user/platform-base", "210987654321")
  aws.base.add_client_error("get_caller_identity", service_error_code="ExpiredToken", http_status_code=403)
  assert not publish_base(store, aws.sts)
  assert store.base is None


def test_status_shows_no_foreign_account_nor_aws_message(store, aws):
  aws.assume()
  aws.caller(account="210987654321")
  reconcile(store, aws, account())
  assert "210987654321" not in last(store)[1]["conditions"][0]["message"]
  aws.base.add_client_error("assume_role", service_error_code="ValidationError", service_message="User arn:aws:iam::210987654321:user/platform-base is not valid", http_status_code=400)
  reconcile(store, aws, account())
  message = last(store)[1]["conditions"][0]["message"]
  assert message == "AssumeRole failed: ValidationError"
