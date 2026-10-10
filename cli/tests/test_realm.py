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
