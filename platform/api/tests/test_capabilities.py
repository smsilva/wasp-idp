"""platform status (#269): capabilities computed from the Deployments that implement them (ADR 0039)."""
import pytest
from fastapi.testclient import TestClient

from platform_api.app import create_app
from platform_api.capabilities import CAPABILITIES_LABEL, IDENTITY_PROVIDERS_ANNOTATION, PROVIDER_LABEL, VENDOR_LABEL
from platform_api.journal import Journal
from fakes import FakeState
from tokens import TokenFactory

BASE = "arn:aws:iam::210987654321:user/platform-base"


def deployment(provider, capabilities, namespace="platform-system", vendor=None, ready=1, image=None, annotations=None):
  labels = {PROVIDER_LABEL: provider, CAPABILITIES_LABEL: capabilities}
  if vendor:
    labels[VENDOR_LABEL] = vendor
  return {
    "name": provider.replace("_", "-") + "-provider", "namespace": namespace, "labels": labels,
    "annotations": annotations or {}, "image": image or f"{provider.replace('_', '-')}-provider:3f9a1c2b7d4e",
    "desired": 1, "ready": ready,
  }


def installed():
  return [
    deployment("keycloak", "identity", "platform-auth", image="quay.io/keycloak/keycloak:26.5.5", annotations={IDENTITY_PROVIDERS_ANNOTATION: "google"}),
    deployment("platform-api", "catalog", image="platform-api:9c1e4b07a2d3"),
    deployment("local_vcluster", "environment"),
    deployment("scm_github", "scm.build", vendor="github"),
    deployment("registry", "registry"),
    deployment("aws_account", "cloud-account", vendor="aws"),
    deployment("forager", "resources"),
    deployment("workload", "workload"),
  ]


class FakeDeployments:
  def __init__(self, items):
    self.items = items

  def list(self):
    return self.items


class FakeBaseIdentity:
  def __init__(self, arn=BASE):
    self.value = arn

  def arn(self):
    return self.value


def connection(name, ready=True, reason=None, vendor="github", default=False):
  condition = {"type": "Ready", "status": "True" if ready else "False", "reason": reason or ("Verified" if ready else "MissingPermissions"), "message": None if ready else "missing: workflows"}
  return {
    "metadata": {"name": name},
    "spec": {"vendor": vendor, "github": {"org": name}, "default": default},
    "status": {"conditions": [condition]},
  }


def account(name, ready=True, vendor="aws"):
  condition = {"type": "Ready", "status": "True" if ready else "False", "reason": "Verified" if ready else "TrustNotEstablished"}
  return {
    "metadata": {"name": name},
    "spec": {"vendor": vendor, "aws": {"roleArn": "arn:aws:iam::123456789012:role/platform"}},
    "status": {"conditions": [condition]},
  }


@pytest.fixture
def tokens():
  return TokenFactory()


@pytest.fixture
def setup(tmp_path, tokens):
  world = {"state": FakeState(), "deployments": installed(), "base": BASE}

  def client():
    app = create_app(
      world["state"], Journal(tmp_path / "journal.jsonl"), tokens.verifier(),
      base_identity=FakeBaseIdentity(world["base"]), deployments=FakeDeployments(world["deployments"]),
    )
    return TestClient(app)

  world["client"] = client
  return world


@pytest.fixture
def admin(tokens):
  return {"Authorization": f"Bearer {tokens.issue(sub='admin-1', group_paths=['/platform-admins', '/platform-users'])}"}


@pytest.fixture
def user(tokens):
  return {"Authorization": f"Bearer {tokens.issue(sub='user-1', group_paths=['/platform-users'])}"}


def statuses(setup, headers):
  return {item["name"]: item["status"] for item in setup["client"]().get("/v1/capabilities", headers=headers).json()["items"]}


def by_name(setup, headers):
  return {item["name"]: item for item in setup["client"]().get("/v1/capabilities", headers=headers).json()["items"]}


def registry(name, ready=True, default=False):
  condition = {"type": "Ready", "status": "True" if ready else "False", "reason": "Reachable" if ready else "Unreachable", "message": None if ready else "https://ghcr.io/v2/: timeout"}
  return {
    "metadata": {"name": name},
    "spec": {"vendor": "ghcr", "host": "ghcr.io", "namespace": name, "default": default},
    "status": {"conditions": [condition]},
  }


def ready_scm(setup):
  setup["state"].stores["scmconnections"]["wasp-foundry"] = connection("wasp-foundry", default=True)
  setup["state"].stores["ociregistries"]["ghcr-wasp-foundry"] = registry("ghcr-wasp-foundry", default=True)


def test_the_subsystems_in_the_order_of_adr_0034(setup, admin):
  items = setup["client"]().get("/v1/capabilities", headers=admin).json()["items"]
  assert [item["name"] for item in items] == ["identity", "catalog", "environment", "scm", "registry", "build", "cloud-account", "resources", "workload"]


def test_all_active(setup, admin):
  ready_scm(setup)
  assert set(statuses(setup, admin).values()) == {"Active"}
  items = by_name(setup, admin)
  assert items["scm"]["detail"] == "wasp-foundry (default)"
  assert items["cloud-account"]["drivers"][0]["baseIdentity"] == BASE
  assert items["identity"]["drivers"][0]["version"] == "26.5.5"
  assert items["workload"]["dependsOn"] == ["environment", "build", "resources", "registry"]
  assert items["registry"]["detail"] == "ghcr-wasp-foundry (default)"


def test_without_a_connection_scm_and_build_are_not_configured(setup, admin):
  items = by_name(setup, admin)
  assert (items["scm"]["status"], items["scm"]["detail"], items["scm"]["fix"]) == ("NotConfigured", "no connection ready", "platform scm connection add <name> --org <org>")
  assert (items["build"]["status"], items["build"]["detail"]) == ("NotConfigured", "needs scm; needs registry")
  assert (items["registry"]["status"], items["registry"]["fix"]) == ("NotConfigured", "platform registry add <name> --scm-connection <connection> --default")


def test_a_connection_not_ready_degrades_scm_and_build(setup, admin):
  ready_scm(setup)
  setup["state"].stores["scmconnections"]["wasp-labs"] = connection("wasp-labs")
  setup["state"].stores["scmconnections"]["acme-payments"] = connection("acme-payments", ready=False, vendor="bitbucket")
  items = by_name(setup, admin)
  assert (items["scm"]["status"], items["scm"]["detail"]) == ("Degraded", "3 connections: 2 ready, 1 MissingPermissions")
  assert items["scm"]["fix"] == "acme-payments: platform scm connection get acme-payments"
  assert [row["name"] for row in items["scm"]["connections"]] == ["acme-payments", "wasp-foundry", "wasp-labs"]
  assert (items["build"]["status"], items["build"]["detail"]) == ("Degraded", "needs scm: acme-payments")


def test_a_registry_not_ready_or_no_default_degrades_registry_and_build(setup, admin):
  ready_scm(setup)
  setup["state"].stores["ociregistries"]["harbor"] = registry("harbor", ready=False)
  items = by_name(setup, admin)
  assert (items["registry"]["status"], items["registry"]["detail"]) == ("Degraded", "2 registries: 1 ready, 1 Unreachable")
  assert items["registry"]["fix"] == "harbor: platform registry get harbor"
  assert (items["build"]["status"], items["build"]["detail"]) == ("Degraded", "needs registry: harbor")
  del setup["state"].stores["ociregistries"]["harbor"]
  setup["state"].stores["ociregistries"]["ghcr-wasp-foundry"] = registry("ghcr-wasp-foundry")
  items = by_name(setup, admin)
  assert (items["registry"]["status"], items["registry"]["detail"], items["registry"]["fix"]) == ("Degraded", "no default registry", "platform registry set-default <name>")


def test_a_driver_without_ready_replicas_is_unreachable(setup, admin):
  ready_scm(setup)
  next(item for item in setup["deployments"] if item["labels"][PROVIDER_LABEL] == "forager")["ready"] = 0
  items = by_name(setup, admin)
  assert (items["resources"]["status"], items["resources"]["detail"]) == ("Unreachable", "forager: 0/1 replicas ready")


def test_one_driver_down_next_to_one_that_works_is_degraded(setup, admin):
  ready_scm(setup)
  setup["deployments"].append(deployment("scm_bitbucket", "scm.build", vendor="bitbucket", ready=0))
  items = by_name(setup, admin)
  assert (items["scm"]["status"], items["scm"]["detail"]) == ("Degraded", "scm_bitbucket: 0/1 replicas ready")
  assert items["scm"]["providers"] == ["scm_bitbucket", "scm_github"]
  assert [found["vendor"] for found in items["scm"]["drivers"]] == ["bitbucket", "github"]


def test_no_driver_is_no_provider(setup, admin):
  setup["deployments"] = [item for item in setup["deployments"] if item["labels"][PROVIDER_LABEL] != "aws_account"]
  items = by_name(setup, admin)
  assert (items["cloud-account"]["status"], items["cloud-account"]["detail"]) == ("NoProviderForCapability", "not installed")


def test_without_a_base_identity_cloud_account_is_not_configured(setup, admin):
  setup["base"] = None
  items = by_name(setup, admin)
  assert (items["cloud-account"]["status"], items["cloud-account"]["fix"]) == ("NotConfigured", "platform init --aws-profile <profile>")


def test_an_account_not_ready_is_its_owners_not_the_platforms(setup, admin):
  for name, ready in (("a", True), ("b", True), ("c", False)):
    setup["state"].stores["cloudaccounts"][name] = account(name, ready)
  items = by_name(setup, admin)
  assert (items["cloud-account"]["status"], items["cloud-account"]["detail"]) == ("Active", "3 accounts: 2 ready, 1 TrustNotEstablished")
  assert items["cloud-account"]["accounts"] == [{"vendor": "aws", "ready": 2, "notReady": {"TrustNotEstablished": 1}}]


def test_without_google_identity_stays_active_with_a_fix(setup, admin):
  setup["deployments"][0]["annotations"] = {}
  items = by_name(setup, admin)
  assert (items["identity"]["status"], items["identity"]["detail"]) == ("Active", "without Google IdP")
  assert "GOOGLE_CLIENT_ID" in items["identity"]["fix"]


def test_a_regular_user_sees_name_and_status_only(setup, user):
  items = setup["client"]().get("/v1/capabilities", headers=user).json()["items"]
  assert all(set(item) == {"name", "status"} for item in items)
  assert setup["client"]().get("/v1/capabilities/scm", headers=user).json() == {"name": "scm", "status": "NotConfigured"}


def test_one_capability(setup, admin):
  body = setup["client"]().get("/v1/capabilities/scm", headers=admin).json()
  assert body["name"] == "scm"
  assert body["connections"] == []


def test_an_unknown_capability_is_404(setup, admin):
  response = setup["client"]().get("/v1/capabilities/nope", headers=admin)
  assert response.status_code == 404
  assert response.json()["error"]["message"] == "capability 'nope' not found (capabilities: identity, catalog, environment, scm, registry, build, cloud-account, resources, workload)"


def test_without_a_deployment_reader_nothing_is_installed(tmp_path, tokens, admin):
  client = TestClient(create_app(FakeState(), Journal(tmp_path / "journal.jsonl"), tokens.verifier()))
  items = client.get("/v1/capabilities", headers=admin).json()["items"]
  assert {item["status"] for item in items} == {"NoProviderForCapability"}


@pytest.mark.parametrize("image,expected", [
  ("forager-provider:d41f8a6c0e37", "d41f8a6c0e37"),
  ("quay.io/keycloak/keycloak:26.5.5", "26.5.5"),
  ("localhost:5000/platform-api", "latest"),
  ("ghcr.io/acme/api:1.2@sha256:" + "a" * 64, "1.2"),
])
def test_version_is_the_image_tag(image, expected):
  from platform_api.capabilities import version
  assert version(image) == expected


# The writes of an optional subsystem need its provider (#377, ADR 0034 §4).
WRITES = [
  ("scm_github", "POST", "/v1/scm/connections", {"name": "acme", "vendor": "github", "org": "acme"}),
  ("scm_github", "DELETE", "/v1/scm/connections/acme", None),
  ("scm_github", "POST", "/v1/catalog/components", {"name": "hello-api", "system": "greeter"}),
  ("registry", "POST", "/v1/registries", {"name": "ghcr-acme", "vendor": "ghcr", "host": "ghcr.io", "namespace": "acme"}),
  ("scm_github", "POST", "/v1/builds", {"component": "hello-api", "branch": "main"}),
  ("aws_account", "POST", "/v1/cloud/accounts", {"name": "nonprod", "vendor": "aws", "roleArn": "arn:aws:iam::123456789012:role/platform"}),
  ("forager", "PUT", "/v1/environments/demo/binding-policy", {"provisioners": []}),
  ("workload", "POST", "/v1/environments/demo/workloads/hello-api/revisions", {"component": "hello-api", "version": "0.1.0"}),
  ("workload", "DELETE", "/v1/environments/demo/workloads/routes/hello-api", None),
]


def without(setup, provider):
  setup["deployments"] = [item for item in setup["deployments"] if item["labels"][PROVIDER_LABEL] != provider]


@pytest.mark.parametrize("provider,method,path,body", WRITES)
def test_a_write_without_its_provider_is_503(setup, admin, provider, method, path, body):
  without(setup, provider)
  response = setup["client"]().request(method, path, json=body, headers=admin)
  assert response.status_code == 503, response.text
  error = response.json()["error"]
  assert error["code"] == "NoProviderForCapability"
  assert error["message"].endswith("has no provider installed: see platform status " + error["message"].split("'")[1])


@pytest.mark.parametrize("provider,method,path,body", WRITES)
def test_with_its_provider_the_route_answers_as_before(setup, admin, provider, method, path, body):
  response = setup["client"]().request(method, path, json=body, headers=admin)
  assert response.status_code != 503, response.text


@pytest.mark.parametrize("provider,path", [
  ("scm_github", "/v1/scm/connections"), ("registry", "/v1/registries"), ("aws_account", "/v1/cloud/accounts"),
  ("workload", "/v1/environments/demo/workloads"),
])
def test_reads_stay_open_without_the_provider(setup, admin, provider, path):
  without(setup, provider)
  assert setup["client"]().get(path, headers=admin).status_code != 503


def test_without_a_token_it_is_401_before_503(setup):
  without(setup, "aws_account")
  assert setup["client"]().post("/v1/cloud/accounts", json={}).status_code == 401


def test_an_unreachable_provider_is_not_503(setup, admin):
  next(item for item in setup["deployments"] if item["labels"][PROVIDER_LABEL] == "registry")["ready"] = 0
  response = setup["client"]().post("/v1/registries", json={"name": "ghcr-acme", "vendor": "ghcr", "host": "ghcr.io", "namespace": "acme"}, headers=admin)
  assert response.status_code != 503
