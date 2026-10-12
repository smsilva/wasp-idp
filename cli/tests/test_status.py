"""platform status (#269): the CLI lays out what /v1/capabilities computes."""
import json

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import client as client_module
from wasp_platform.cli import app

runner = CliRunner()


def driver(provider, vendor=None, version="3f9a1c2b7d4e", ready=1, status="Active", **extra):
  return {"provider": provider, "vendor": vendor, "deployment": f"platform-system/{provider}", "version": version, "replicas": {"desired": 1, "ready": ready}, "status": status, **extra}


def capability(name, status="Active", providers=(), detail=None, fix=None, depends_on=(), drivers=None, **extra):
  return {
    "name": name, "status": status, "providers": list(providers), "detail": detail, "fix": fix, "dependsOn": list(depends_on),
    "drivers": drivers if drivers is not None else [driver(provider) for provider in providers], **extra,
  }


SCM = capability(
  "scm", "Degraded", ["scm_bitbucket", "scm_github"], "3 connections: 2 ready, 1 MissingPermissions",
  "acme-payments: platform scm connection get acme-payments", ["identity", "catalog"],
  drivers=[driver("scm_bitbucket", "bitbucket", "71c0e9a4b2d8"), driver("scm_github", "github")],
  connections=[
    {"name": "acme-payments", "vendor": "bitbucket", "org": "acme-payments", "default": False, "status": "MissingPermissions", "message": "missing repository:admin"},
    {"name": "wasp-foundry", "vendor": "github", "org": "wasp-foundry", "default": True, "status": "ready", "message": None},
  ],
)
CLOUD = capability(
  "cloud-account", "Active", ["aws_account"], "4 accounts: 3 ready, 1 TrustNotEstablished", depends_on=["identity"],
  drivers=[driver("aws_account", "aws", "b72d90e1f4a6", baseIdentity="arn:aws:iam::123456789012:user/platform")],
  accounts=[{"vendor": "aws", "ready": 3, "notReady": {"TrustNotEstablished": 1}}],
)
ADMIN = [
  capability("identity", "Active", ["keycloak"], "without Google IdP", "platform init with GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET set", drivers=[driver("keycloak", version="26.5.5")]),
  capability("catalog", "Active", ["platform-api"], depends_on=["identity"]),
  SCM,
  capability("build", "Degraded", ["scm_bitbucket", "scm_github"], "needs scm: acme-payments", depends_on=["scm", "catalog"]),
  CLOUD,
  capability("resources", "NoProviderForCapability", [], "not installed", depends_on=["environment", "build", "catalog"]),
]


def user_view(items):
  return [{"name": item["name"], "status": item["status"]} for item in items]


@pytest.fixture
def api(monkeypatch):
  state = {"items": ADMIN, "requests": [], "error": None}

  def handler(request: httpx.Request) -> httpx.Response:
    state["requests"].append(request)
    if state["error"]:
      return httpx.Response(state["error"][0], json={"error": {"code": "x", "message": state["error"][1]}})
    name = request.url.path.removeprefix("/v1/capabilities").strip("/")
    if not name:
      return httpx.Response(200, json={"items": state["items"]})
    return httpx.Response(200, json=next(item for item in state["items"] if item["name"] == name))

  transport = httpx.MockTransport(handler)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(
    client_module.PlatformClient, "__init__",
    lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token or (lambda: "test-token")),
  )
  return state


def run(*args):
  return runner.invoke(app, ["status", *args])


def test_admin_table(api):
  result = run()
  assert result.exit_code == 1
  lines = result.stdout.splitlines()
  assert lines[0].split() == ["CAPABILITY", "STATUS", "PROVIDERS", "DETAIL"]
  assert lines[3].split() == ["scm", "Degraded", "scm_bitbucket,", "scm_github", "3", "connections:", "2", "ready,", "1", "MissingPermissions"]
  assert lines[6].split()[:3] == ["resources", "NoProviderForCapability", "—"]
  assert "✗ 2 of 5 installed capabilities not Active: scm, build" in result.output
  assert "details and the fix: platform status <capability>" in result.output


def test_user_table(api):
  api["items"] = user_view(ADMIN)
  result = run()
  assert result.exit_code == 1
  assert result.stdout.splitlines()[0].split() == ["CAPABILITY", "STATUS"]
  assert "ask a platform-admin to configure them" in result.output


def test_all_active_exits_0(api):
  api["items"] = [capability("identity", providers=["keycloak"]), capability("catalog", providers=["platform-api"])]
  result = run()
  assert result.exit_code == 0, result.output
  assert result.stdout.splitlines()[-1] == "✓ all 2 capabilities Active"


def test_not_installed_is_no_failure(api):
  api["items"] = [capability("identity", providers=["keycloak"]), capability("cloud-account", "NoProviderForCapability", detail="not installed")]
  result = run()
  assert result.exit_code == 0, result.output
  assert result.stdout.splitlines()[-1] == "✓ all 1 installed capabilities Active (1 not installed: cloud-account)"


def test_one_capability_with_drivers_and_connections(api):
  result = run("scm")
  assert result.exit_code == 1
  assert api["requests"][0].url.path == "/v1/capabilities/scm"
  assert result.stdout.splitlines() == [
    "scm  Degraded",
    "  depends on    identity, catalog",
    "  detail        3 connections: 2 ready, 1 MissingPermissions",
    "  fix           acme-payments: platform scm connection get acme-payments",
    "",
    "  DRIVER     PROVIDER       VERSION       REPLICAS  STATUS",
    "  bitbucket  scm_bitbucket  71c0e9a4b2d8  1/1       Active",
    "  github     scm_github     3f9a1c2b7d4e  1/1       Active",
    "",
    "  CONNECTION              VENDOR     ORG            STATUS",
    "  acme-payments           bitbucket  acme-payments  MissingPermissions: missing repository:admin",
    "  wasp-foundry (default)  github     wasp-foundry   Ready",
  ]


def test_cloud_account_shows_base_identity_and_counts(api):
  result = run("cloud-account")
  assert result.exit_code == 0, result.output
  lines = result.stdout.splitlines()
  assert lines[4].split() == ["DRIVER", "PROVIDER", "VERSION", "REPLICAS", "BASE", "IDENTITY", "STATUS"]
  assert lines[5].split() == ["aws", "aws_account", "b72d90e1f4a6", "1/1", "arn:aws:iam::123456789012:user/platform", "Active"]
  assert lines[8].split() == ["aws", "3", "1", "(TrustNotEstablished)"]
  assert lines[-1] == "  accounts by owner: platform cloud account list"


def test_registry_lists_its_registries(api):
  api["items"] = [capability(
    "registry", "Degraded", ["registry"], "no default registry", "platform registry set-default <name>", ["identity"],
    registries=[{"name": "ghcr-wasp-foundry", "vendor": "ghcr", "address": "ghcr.io/wasp-foundry", "default": False, "status": "ready", "message": None}],
  )]
  result = run("registry")
  assert result.exit_code == 1
  assert result.stdout.splitlines()[-2:] == [
    "  REGISTRY           VENDOR  ADDRESS               STATUS",
    "  ghcr-wasp-foundry  ghcr    ghcr.io/wasp-foundry  Ready",
  ]


def test_one_capability_as_a_user(api):
  api["items"] = user_view(ADMIN)
  result = run("scm")
  assert result.exit_code == 1
  assert result.stdout.splitlines() == ["scm  Degraded", "  ask a platform-admin to configure it"]


def test_a_provider_without_vendor_has_no_driver_column(api):
  result = run("catalog")
  assert result.exit_code == 0, result.output
  assert result.stdout.splitlines()[3].split() == ["PROVIDER", "VERSION", "REPLICAS", "STATUS"]


def test_verbose_prints_every_block_and_the_summary(api):
  result = run("--verbose")
  assert result.exit_code == 1
  headers = [line for line in result.stdout.splitlines() if line and not line.startswith(" ")]
  assert headers == ["identity  Active", "catalog  Active", "scm  Degraded", "build  Degraded", "cloud-account  Active", "resources  NoProviderForCapability"]
  assert "✗ 2 of 5 installed capabilities not Active: scm, build" in result.output


def test_json_keeps_the_exit_code(api):
  result = run("--output", "json")
  assert result.exit_code == 1
  assert [item["name"] for item in json.loads(result.stdout)["items"]][:2] == ["identity", "catalog"]
  single = run("scm", "--output", "json")
  assert json.loads(single.stdout)["status"] == "Degraded"


def test_an_unknown_capability(api):
  api["error"] = (404, "capability 'nope' not found (capabilities: identity, catalog)")
  result = run("nope")
  assert result.exit_code == 1
  assert "capability 'nope' not found" in result.output
