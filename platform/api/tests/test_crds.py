"""The CRDs and the API agree on group, kinds and required fields."""
from pathlib import Path

import pytest
import yaml

from fakes import FakeState
from platform_api.state import CATALOG_GROUP, CATALOG_PLURALS, GROUP, group_of

CRDS = Path(__file__).parents[3] / "platform" / "crds"


def load(plural: str) -> dict:
  return yaml.safe_load((CRDS / f"catalog-{plural.removesuffix('s')}.yaml").read_text())


@pytest.mark.parametrize("plural,required", [
  ("domains", ["owner"]),
  ("systems", ["owner", "domain"]),
  ("resources", ["owner", "type", "system"]),
  ("templates", ["owner", "type", "source"]),
])
def test_catalog_crd(plural, required):
  crd = load(plural)
  assert crd["metadata"]["name"] == f"{plural}.{CATALOG_GROUP}"
  assert crd["spec"]["group"] == CATALOG_GROUP
  assert crd["spec"]["names"]["plural"] == plural
  spec = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["spec"]
  assert sorted(spec["required"]) == sorted(required)


def test_template_crd_matches_the_api():
  from platform_api.templates import TYPES

  version = load("templates")["spec"]["versions"][0]
  spec = version["schema"]["openAPIV3Schema"]["properties"]["spec"]["properties"]
  assert tuple(spec["type"]["enum"]) == TYPES
  assert sorted(spec["source"]["required"]) == ["path", "ref", "repo"]
  # The CLI fetches repo and ref with git: a CR written straight to the cluster must obey the same rules.
  from platform_api.templates import REF, REPO_URL

  assert spec["source"]["properties"]["repo"]["pattern"] == REPO_URL.pattern
  assert spec["source"]["properties"]["ref"]["pattern"] == REF.pattern
  assert [column["name"] for column in version["additionalPrinterColumns"]] == ["Type", "Default", "Ref"]


def test_group_of():
  assert group_of("environments") == GROUP
  assert all(group_of(plural) == CATALOG_GROUP for plural in CATALOG_PLURALS)


def test_stores_are_per_plural():
  state = FakeState()
  state.create("domains", {"metadata": {"name": "greeter"}, "spec": {}})
  state.create("systems", {"metadata": {"name": "greeter"}, "spec": {}})
  assert state.get("domains", "greeter")["metadata"]["uid"] != state.get("systems", "greeter")["metadata"]["uid"]
  assert state.list("environments") == []


def test_api_role_can_update_catalog():
  deploy = Path(__file__).parents[1] / "deploy" / "platform-api.yaml"
  role = next(doc for doc in yaml.safe_load_all(deploy.read_text()) if doc and doc["kind"] == "Role")
  rule = next(rule for rule in role["rules"] if CATALOG_GROUP in rule["apiGroups"])
  assert {"create", "update", "delete"} <= set(rule["verbs"])


def test_cloud_account_crd_matches_the_api():
  from platform_api.cloud_accounts import CLOUD_ACCOUNTS, VENDORS

  crd = yaml.safe_load((CRDS / "cloudaccount.yaml").read_text())
  assert crd["metadata"]["name"] == f"{CLOUD_ACCOUNTS}.{GROUP}"
  assert group_of(CLOUD_ACCOUNTS) == GROUP
  version = crd["spec"]["versions"][0]
  spec = version["schema"]["openAPIV3Schema"]["properties"]["spec"]["properties"]
  assert tuple(spec["vendor"]["enum"]) == VENDORS
  assert sorted(spec["aws"]["required"]) == ["externalId", "roleArn"]
  assert "observedVerifyRequest" in version["schema"]["openAPIV3Schema"]["properties"]["status"]["properties"]


def test_scm_connection_crd():
  from platform_api.scm import ORG, PLURAL

  crd = yaml.safe_load((CRDS / "scm-connection.yaml").read_text())
  assert crd["metadata"]["name"] == f"{PLURAL}.{GROUP}"
  assert crd["spec"]["names"]["shortNames"] == ["scm"]
  version = crd["spec"]["versions"][0]
  assert version["subresources"] == {"status": {}}
  spec = version["schema"]["openAPIV3Schema"]["properties"]["spec"]["properties"]
  assert spec["vendor"]["enum"] == ["github"]
  assert spec["github"]["properties"]["org"]["pattern"] == ORG.pattern
  assert [column["name"] for column in version["additionalPrinterColumns"]] == ["Vendor", "Org", "Default", "Ready", "Reason"]


def test_api_role_writes_secrets_but_never_reads_them():
  deploy = Path(__file__).parents[1] / "deploy" / "platform-api.yaml"
  role = next(doc for doc in yaml.safe_load_all(deploy.read_text()) if doc and doc["kind"] == "Role")
  verbs = {verb for rule in role["rules"] if "secrets" in rule["resources"] for verb in rule["verbs"]}
  assert verbs == {"create", "update", "patch", "delete"}
  scm = next(rule for rule in role["rules"] if "scmconnections" in rule["resources"])
  assert {"get", "list", "create", "update", "delete"} <= set(scm["verbs"])
  assert any("scmconnections/status" in rule["resources"] for rule in role["rules"])


def test_component_creation_crd_matches_the_api():
  from platform_api.components import CREATIONS, PRD_MAX

  crd = yaml.safe_load((CRDS / "componentcreation.yaml").read_text())
  assert crd["metadata"]["name"] == f"{CREATIONS}.{GROUP}"
  assert group_of(CREATIONS) == GROUP
  version = crd["spec"]["versions"][0]
  assert version["subresources"] == {"status": {}}
  spec = version["schema"]["openAPIV3Schema"]["properties"]["spec"]["properties"]
  assert spec["prd"]["maxLength"] == PRD_MAX
  assert spec["visibility"]["enum"] == ["public", "private"]


def test_component_index_crd():
  from platform_api.components import COMPONENTS

  crd = load(COMPONENTS)
  assert crd["metadata"]["name"] == f"{COMPONENTS}.{CATALOG_GROUP}"
  assert group_of(COMPONENTS) == CATALOG_GROUP
  # A read mirror: the API never writes it.
  deploy = Path(__file__).parents[1] / "deploy" / "platform-api.yaml"
  role = next(doc for doc in yaml.safe_load_all(deploy.read_text()) if doc and doc["kind"] == "Role")
  verbs = {verb for rule in role["rules"] if COMPONENTS in rule["resources"] for verb in rule["verbs"]}
  assert verbs == {"get", "list", "watch"}


def test_build_crd_matches_the_api():
  from platform_api.builds import BUILDS, VERSION_PATTERN

  crd = yaml.safe_load((CRDS / "build.yaml").read_text())
  assert crd["metadata"]["name"] == f"{BUILDS}.{GROUP}"
  assert group_of(BUILDS) == GROUP
  version = crd["spec"]["versions"][0]
  assert version["subresources"] == {"status": {}}
  spec = version["schema"]["openAPIV3Schema"]["properties"]["spec"]
  assert spec["properties"]["version"]["pattern"] == f"^{VERSION_PATTERN.pattern}$"
  assert sorted(spec["required"]) == ["branch", "component", "repo", "requestId", "scmConnection"]


def test_version_index_crd():
  from platform_api.builds import VERSIONS

  crd = load(VERSIONS)
  assert crd["metadata"]["name"] == f"{VERSIONS}.{CATALOG_GROUP}"
  assert group_of(VERSIONS) == CATALOG_GROUP
  # A read mirror: the API never writes it.
  deploy = Path(__file__).parents[1] / "deploy" / "platform-api.yaml"
  role = next(doc for doc in yaml.safe_load_all(deploy.read_text()) if doc and doc["kind"] == "Role")
  verbs = {verb for rule in role["rules"] if VERSIONS in rule["resources"] for verb in rule["verbs"]}
  assert verbs == {"get", "list", "watch"}
  # The Workload Spec (#291): any Score, kept as written, and absent from versions indexed before it.
  spec = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["spec"]
  assert spec["properties"]["appSpec"]["x-kubernetes-preserve-unknown-fields"] is True
  assert "appSpec" not in spec["required"]
