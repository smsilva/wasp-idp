import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app

runner = CliRunner()
ROLE = "arn:aws:iam::123456789012:role/platform"
POLICY = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::210987654321:user/platform-base"}, "Action": "sts:AssumeRole", "Condition": {"StringEquals": {"sts:ExternalId": "generated"}}}]}


class FakeApi:
  def __init__(self):
    self.accounts = {}
    self.requests = []
    self.groups = ["platform-users"]
    self.answers_after = 1  # GETs until the provider answers a verify
    self.outcome = ("ready", None)

  def handler(self, request: httpx.Request) -> httpx.Response:
    self.requests.append(request)
    path = request.url.path
    if path == "/v1/me":
      return httpx.Response(200, json={"sub": "u-1", "groups": self.groups})
    parts = path.split("/")[4:]
    if not parts and request.method == "POST":
      body = json.loads(request.content)
      account = {"name": body["name"], "vendor": body["vendor"], "roleArn": body["roleArn"], "regions": body["regions"], "accountId": "123456789012",
                 "status": "pending", "message": None, "lastValidated": None, "verifyPending": False, "owner": "dev@example.com"}
      self.accounts[body["name"]] = account
      return httpx.Response(202, json={**account, "trustPolicy": POLICY})
    if not parts:
      return httpx.Response(200, json={"items": list(self.accounts.values())})
    account = self.accounts.get(parts[0])
    if account is None:
      return httpx.Response(404, json={"error": {"code": "not_found", "message": f"cloud account '{parts[0]}' not found"}})
    if request.method == "DELETE":
      del self.accounts[parts[0]]
      return httpx.Response(202, json={"name": parts[0], "status": "deleting"})
    if request.method == "POST":
      account["verifyPending"] = True
      self.pending = self.answers_after
      return httpx.Response(202, json=account)
    if account["verifyPending"]:
      self.pending -= 1
      if self.pending <= 0:
        account.update(verifyPending=False, status=self.outcome[0], message=self.outcome[1], lastValidated="2026-10-11T12:00:00Z")
    return httpx.Response(200, json={**account, "trustPolicy": POLICY})


@pytest.fixture
def api(monkeypatch):
  fake = FakeApi()
  transport = httpx.MockTransport(fake.handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  monkeypatch.setattr("wasp_platform.commands.cloud.time.sleep", lambda seconds: None)
  return fake


def run(*args):
  return runner.invoke(app, ["cloud", "account", *args])


def test_add_prints_the_trust_policy(api):
  result = run("add", "nonprod", "--role-arn", ROLE, "--region", "us-east-1")
  assert result.exit_code == 0, result.output
  assert json.loads(api.requests[-1].content) == {"name": "nonprod", "vendor": "aws", "roleArn": ROLE, "regions": ["us-east-1"]}
  assert "✓ cloud account nonprod added (pending)" in result.output
  assert '"sts:ExternalId": "generated"' in result.output
  assert "platform cloud account verify nonprod --wait" in result.output


def test_list_shows_owner_only_to_admins(api):
  run("add", "nonprod", "--role-arn", ROLE)
  assert run("list").output.split()[:5] == ["NAME", "VENDOR", "ACCOUNT", "STATUS", "VALIDATED"]
  assert "OWNER" not in run("list").output
  api.groups = ["platform-admins"]
  output = run("list").output
  assert "OWNER" in output and "dev@example.com" in output


def test_get_includes_the_trust_policy(api):
  run("add", "nonprod", "--role-arn", ROLE)
  output = run("get", "nonprod").output
  assert "nonprod: pending" in output and "123456789012" in output and "sts:ExternalId" in output


def test_verify_wait_until_ready(api):
  run("add", "nonprod", "--role-arn", ROLE)
  api.answers_after = 2
  result = run("verify", "nonprod", "--wait")
  assert result.exit_code == 0, result.output
  assert "✓ nonprod ready (account 123456789012)" in result.output


def test_verify_wait_reports_the_failure(api):
  run("add", "nonprod", "--role-arn", ROLE)
  api.outcome = ("ExternalIdNotEnforced", "add the sts:ExternalId condition")
  result = run("verify", "nonprod", "--wait")
  assert result.exit_code == 1
  assert "ExternalIdNotEnforced — add the sts:ExternalId condition" in result.output


def test_verify_without_wait_returns_at_once(api):
  run("add", "nonprod", "--role-arn", ROLE)
  assert "nonprod: verification requested" in run("verify", "nonprod").output


def test_remove_and_errors(api):
  run("add", "nonprod", "--role-arn", ROLE)
  assert "✓ cloud account nonprod removed" in run("remove", "nonprod").output
  result = run("get", "nonprod")
  assert result.exit_code == 1
  assert "404: cloud account 'nonprod' not found" in result.output


def test_json_output(api):
  account = json.loads(run("add", "nonprod", "--role-arn", ROLE, "--output", "json").output)
  assert account["trustPolicy"] == POLICY
  assert [item["name"] for item in json.loads(run("list", "--output", "json").output)] == ["nonprod"]


def test_base_credential_from_a_profile(monkeypatch):
  from wasp_platform.bootstrap import local

  calls = []
  exported = {"Version": 1, "AccessKeyId": "AKIAEXAMPLE", "SecretAccessKey": "secret", "SessionToken": "token", "Expiration": "2026-10-11T20:00:00+00:00"}
  monkeypatch.setattr(local, "_run", lambda *command, **kwargs: calls.append(command) or json.dumps(exported))
  credential = local.aws_base_credential("platform-base")
  assert calls == [("aws", "configure", "export-credentials", "--profile", "platform-base", "--format", "process")]
  assert credential == {
    "values": {"AWS_ACCESS_KEY_ID": "AKIAEXAMPLE", "AWS_SECRET_ACCESS_KEY": "secret", "AWS_SESSION_TOKEN": "token"},
    "expiration": "2026-10-11T20:00:00+00:00",
  }
  exported = {"Version": 1, "AccessKeyId": "AKIAEXAMPLE", "SecretAccessKey": "secret"}
  assert local.aws_base_credential("platform-base") == {"values": {"AWS_ACCESS_KEY_ID": "AKIAEXAMPLE", "AWS_SECRET_ACCESS_KEY": "secret"}, "expiration": None}
