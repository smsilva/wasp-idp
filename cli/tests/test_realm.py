from pathlib import Path

import yaml

from wasp_platform.bootstrap.local import render_realm

REALM = yaml.safe_load((Path(__file__).parents[2] / "platform" / "keycloak" / "realm-platform.yaml").read_text())


def test_realm_keeps_google_and_bootstrap_admin():
  realm = render_realm(REALM, google=True, admin=True)
  assert [idp["alias"] for idp in realm["identityProviders"]] == ["google"]
  assert [m["name"] for m in realm["identityProviderMappers"]] == ["bootstrap-admin"]


def test_realm_without_google_has_no_identity_provider():
  realm = render_realm(REALM, google=False, admin=True)
  assert "identityProviders" not in realm
  assert "identityProviderMappers" not in realm


def test_realm_without_admin_drops_bootstrap_mapper():
  realm = render_realm(REALM, google=True, admin=False)
  assert realm["identityProviders"]
  assert realm["identityProviderMappers"] == []


def test_cli_client_gets_audience_and_groups():
  client = next(c for c in REALM["clients"] if c["clientId"] == "platform-cli")
  assert {"platform-groups", "platform-api-audience"} <= set(client["defaultClientScopes"])
  assert client["publicClient"] and client["attributes"]["pkce.code.challenge.method"] == "S256"


def test_theme_configmap_flattens_paths():
  from wasp_platform.bootstrap.local import theme_configmap
  theme = Path(__file__).parents[2] / "platform" / "keycloak" / "theme" / "platform"
  data = theme_configmap(theme)["data"]
  assert "login__theme.properties" in data
  assert "login__resources__css__platform.css" in data
  assert "login__messages__messages_pt_BR.properties" in data
  assert "parent=keycloak.v2" in data["login__theme.properties"]


def test_theme_messages_have_the_same_keys():
  messages = Path(__file__).parents[2] / "platform" / "keycloak" / "theme" / "platform" / "login" / "messages"
  def keys(name):
    return {line.split("=", 1)[0] for line in (messages / name).read_text().splitlines() if line and not line.startswith("#")}
  assert keys("messages_en.properties") == keys("messages_pt_BR.properties")


def test_realm_uses_platform_theme():
  assert REALM["loginTheme"] == "platform"
  assert set(REALM["supportedLocales"]) == {"pt-BR", "en"}


SMOKE = yaml.safe_load((Path(__file__).parents[2] / "platform" / "keycloak" / "realm-smoke.yaml").read_text())
SMOKE_USERS = [u["username"] for u in SMOKE["users"]]


def test_realm_without_smoke_has_no_test_client_nor_users():
  realm = render_realm(REALM, google=True, admin=True)
  assert "platform-smoke" not in [c["clientId"] for c in realm["clients"]]
  assert [u["username"] for u in realm["users"]] == ["service-account-platform-api-admin"]


def test_smoke_adds_password_client_and_three_users():
  realm = render_realm(REALM, google=True, admin=True, smoke=SMOKE)
  client = next(c for c in realm["clients"] if c["clientId"] == "platform-smoke")
  assert client["directAccessGrantsEnabled"] is True and client["publicClient"] is True
  assert {"platform-groups", "platform-api-audience"} <= set(client["defaultClientScopes"])
  users = {u["username"]: u for u in realm["users"]}
  assert users["platform-smoke"]["groups"] == ["/platform-users"]
  assert set(users["platform-smoke-admin"]["groups"]) == {"/platform-admins", "/platform-users"}
  assert users["platform-smoke-member"]["groups"] == ["/platform-users"]
  # Passwords come from the Secret keycloak-smoke-user, never from the file.
  assert all(users[name]["credentials"][0]["value"].startswith("$(env:") for name in SMOKE_USERS)
  # The base realm is not mutated: a later render without smoke stays clean.
  assert [u["username"] for u in REALM["users"]] == ["service-account-platform-api-admin"]


def test_cli_client_never_gets_password_grant():
  realm = render_realm(REALM, google=True, admin=True, smoke=SMOKE)
  client = next(c for c in realm["clients"] if c["clientId"] == "platform-cli")
  assert client["directAccessGrantsEnabled"] is False


def test_smoke_passwords_match_the_secret_keys():
  from wasp_platform.bootstrap.local import SMOKE_KEYS
  values = {u["username"]: u["credentials"][0]["value"] for u in SMOKE["users"]}
  assert values == {user: f"$(env:{key})" for user, key in SMOKE_KEYS.items()}


def test_api_admin_client_only_reads_through_roles():
  client = next(c for c in REALM["clients"] if c["clientId"] == "platform-api-admin")
  assert client["serviceAccountsEnabled"] is True and client["publicClient"] is False
  assert not client["standardFlowEnabled"] and not client["directAccessGrantsEnabled"]
  assert client["secret"] == "$(env:PLATFORM_API_ADMIN_SECRET)"
  account = next(u for u in REALM["users"] if u.get("serviceAccountClientId") == "platform-api-admin")
  # Read-only: the writes come from the fine-grained admin permissions init applies (#238).
  assert set(account["clientRoles"]["realm-management"]) == {"view-users", "query-users", "query-groups"}


def test_realm_declares_no_teams():
  # Teams live under /teams, created by the API: keycloak-config-cli must never own that tree.
  assert "teams" not in [g["name"] for g in REALM["groups"]]


def test_seed_templates_first_install_marks_one_default_per_type(tmp_path):
  from wasp_platform.bootstrap.local import SEED_REPO, seed_templates

  root = Path(__file__).parents[2]
  manifests = seed_templates(root, "abc1234", existing=[])
  assert [manifest["metadata"]["name"] for manifest in manifests] == ["python-service"]
  spec = manifests[0]["spec"]
  assert spec["source"] == {"repo": SEED_REPO, "path": "platform/templates/python-service/content", "ref": "abc1234"}
  assert (spec["type"], spec["default"], spec["owner"]) == ("service", True, "team-platform")
  assert spec["parameters"]["properties"]["port"]["default"] == 8000
  assert manifests[0]["apiVersion"] == "catalog.platform.wasp.silvios.me/v1alpha1"


def test_seed_templates_again_keeps_the_admin_choice_of_default():
  from wasp_platform.bootstrap.local import seed_templates

  root = Path(__file__).parents[2]
  # An admin made another service template the default: init must not take it back.
  existing = [
    {"metadata": {"name": "python-service"}, "spec": {"type": "service"}},
    {"metadata": {"name": "go-service"}, "spec": {"type": "service", "default": True}},
  ]
  spec = seed_templates(root, "def5678", existing)[0]["spec"]
  assert "default" not in spec and spec["source"]["ref"] == "def5678"
  # Still the default from an earlier init: stays the default.
  existing = [{"metadata": {"name": "python-service"}, "spec": {"type": "service", "default": True}}]
  assert seed_templates(root, "def5678", existing)[0]["spec"]["default"] is True


def test_seed_ref_is_the_last_commit_on_the_remote(monkeypatch):
  from wasp_platform.bootstrap import local

  answers = {
    ("git", "-C", "/r", "rev-parse", "HEAD"): "local-only\n",
    ("git", "-C", "/r", "branch", "--remotes", "--contains", "local-only"): "",
    ("git", "-C", "/r", "merge-base", "HEAD", "origin/main"): "pushed\n",
  }
  monkeypatch.setattr(local, "_run", lambda *command, **kwargs: answers[command])
  assert local.seed_ref(Path("/r")) == "pushed"
  answers[("git", "-C", "/r", "branch", "--remotes", "--contains", "local-only")] = "  origin/feat/x\n"
  assert local.seed_ref(Path("/r")) == "local-only"
