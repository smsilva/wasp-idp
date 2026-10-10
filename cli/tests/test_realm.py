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
