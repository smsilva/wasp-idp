import base64
import hashlib
import json
import stat
import threading
import time
import urllib.parse
import urllib.request

import httpx
import pytest
from typer.testing import CliRunner

from wasp_platform import auth, client as client_module
from wasp_platform.cli import app

ISSUER = "http://idp.test/realms/platform"
runner = CliRunner()


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
  monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
  return tmp_path


class FakeIdp:
  """Keycloak stand-in: discovery, token (code, device, refresh) and revocation endpoints."""

  def __init__(self):
    self.verifiers = {}
    self.device_polls = 0
    self.revoked = []
    self.refreshed = 0
    self.refresh_clients = []
    self.password_logins = []

  def handler(self, request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/.well-known/openid-configuration"):
      base = f"{ISSUER}/protocol/openid-connect"
      return httpx.Response(200, json={
        "authorization_endpoint": f"{base}/auth", "token_endpoint": f"{base}/token",
        "device_authorization_endpoint": f"{base}/auth/device", "revocation_endpoint": f"{base}/revoke",
      })
    form = dict(urllib.parse.parse_qsl(request.content.decode()))
    if path.endswith("/auth/device"):
      assert form["code_challenge_method"] == "S256"
      self.device_challenge = form["code_challenge"]
      return httpx.Response(200, json={"device_code": "dev-1", "user_code": "ABCD-EFGH", "verification_uri": "http://idp.test/device",
                                       "verification_uri_complete": "http://idp.test/device?user_code=ABCD-EFGH", "interval": 1, "expires_in": 60})
    if path.endswith("/revoke"):
      self.revoked.append(form["token"])
      self.revoke_clients = getattr(self, "revoke_clients", []) + [form["client_id"]]
      return httpx.Response(200)
    grant = form["grant_type"]
    if grant == "authorization_code":
      challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
      if self.verifiers.get(form["code"]) != challenge:
        return httpx.Response(400, json={"error": "invalid_grant"})
      return self.tokens("browser")
    if grant.endswith("device_code"):
      challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
      assert challenge == self.device_challenge
      self.device_polls += 1
      if self.device_polls == 1:
        return httpx.Response(400, json={"error": "authorization_pending"})
      if self.device_polls == 2:
        return httpx.Response(400, json={"error": "slow_down"})
      return self.tokens("device")
    if grant == "refresh_token":
      self.refreshed += 1
      self.refresh_clients.append(form["client_id"])
      return self.tokens("refreshed")
    if grant == "password":
      self.password_logins.append((form["client_id"], form["username"], form["password"], form["scope"]))
      if form["password"] != "right":
        return httpx.Response(401, json={"error": "invalid_grant", "error_description": "Invalid user credentials"})
      return self.tokens("password")
    return httpx.Response(400, json={"error": "unsupported_grant_type"})

  def tokens(self, label):
    return httpx.Response(200, json={"access_token": f"access-{label}", "refresh_token": f"refresh-{label}", "expires_in": 300})


@pytest.fixture
def idp():
  return FakeIdp()


@pytest.fixture
def oidc(idp):
  return auth.Oidc(issuer=ISSUER, client_id="platform-cli", transport=httpx.MockTransport(idp.handler))


def browser_that_consents(idp):
  """Plays the user's browser: approves and follows the redirect to the CLI's 127.0.0.1 listener."""
  def open_browser(url):
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    assert query["code_challenge_method"] == "S256" and query["kc_idp_hint"] == "google"
    idp.verifiers["code-1"] = query["code_challenge"]
    callback = f"{query['redirect_uri']}?code=code-1&state={query['state']}"
    threading.Thread(target=lambda: urllib.request.urlopen(callback).read(), daemon=True).start()
    return True
  return open_browser


def test_browser_login_with_pkce(idp, oidc):
  tokens = oidc.login_browser(open_browser=browser_that_consents(idp), timeout=10)
  assert tokens["access_token"] == "access-browser"


def test_browser_login_rejects_wrong_state(oidc):
  def attacker(url):
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    callback = f"{query['redirect_uri']}?code=stolen&state=forged"
    threading.Thread(target=lambda: _ignore_http_error(callback), daemon=True).start()
    return True
  with pytest.raises(auth.AuthError, match="state mismatch"):
    oidc.login_browser(open_browser=attacker, timeout=10)


def _ignore_http_error(url):
  try:
    urllib.request.urlopen(url)
  except Exception:
    pass


def test_device_login_handles_pending_and_slow_down(idp, oidc):
  shown, waits = [], []
  tokens = oidc.login_device(lambda code, url: shown.append((code, url)), open_browser=lambda url: False, sleep=waits.append)
  assert tokens["access_token"] == "access-device"
  assert shown == [("ABCD-EFGH", "http://idp.test/device?user_code=ABCD-EFGH")]
  assert waits == [1, 1, 6]  # slow_down adds 5 seconds (RFC 8628)


def test_credentials_file_is_private(config_home):
  auth.save_credentials({"access_token": "a", "refresh_token": "r", "expires_in": 300})
  mode = stat.S_IMODE(auth.credentials_path().stat().st_mode)
  assert mode == 0o600


def test_access_token_refreshes_near_expiry(idp, oidc):
  auth.save_credentials({"access_token": "old", "refresh_token": "refresh-old", "expires_in": 30})
  assert auth.access_token(oidc_factory=lambda: oidc) == "access-refreshed"
  assert idp.refreshed == 1
  assert auth.access_token(oidc_factory=lambda: oidc) == "access-refreshed"
  assert idp.refreshed == 1


def test_access_token_without_login():
  with pytest.raises(auth.AuthError, match="platform login"):
    auth.access_token()


def api_transport(seen):
  def handler(request):
    seen.append(request.headers.get("authorization"))
    if request.headers.get("authorization") != "Bearer good":
      return httpx.Response(401, json={"error": {"code": "unauthorized", "message": "invalid token"}})
    return httpx.Response(200, json={"sub": "u1", "email": "dev@example.com", "groups": ["platform-admins", "platform-users"]})
  return httpx.MockTransport(handler)


@pytest.fixture
def api(monkeypatch):
  seen = []
  transport = api_transport(seen)
  original = client_module.PlatformClient.__init__
  monkeypatch.setattr(client_module.PlatformClient, "__init__",
                      lambda self, base_url=None, transport_=None, token=None: original(self, "http://api.test", transport, token))
  return seen


def test_whoami_sends_bearer_and_prints_groups(api):
  auth.save_credentials({"access_token": "good", "refresh_token": "r", "expires_in": 300})
  result = runner.invoke(app, ["whoami"])
  assert result.exit_code == 0, result.output
  assert result.output.strip() == "dev@example.com (platform-admins, platform-users)"
  assert api == ["Bearer good"]


def test_whoami_json(api):
  auth.save_credentials({"access_token": "good", "refresh_token": "r", "expires_in": 300})
  assert json.loads(runner.invoke(app, ["whoami", "--output", "json"]).output)["email"] == "dev@example.com"


def test_whoami_after_logout_asks_for_login(api, monkeypatch):
  auth.save_credentials({"access_token": "good", "refresh_token": "r", "expires_in": 300})
  monkeypatch.setattr(auth.Oidc, "__init__", lambda self, *a, **k: (_ for _ in ()).throw(auth.AuthError("no idp")))
  assert runner.invoke(app, ["logout"]).exit_code == 0
  result = runner.invoke(app, ["whoami"])
  assert result.exit_code == 1
  assert "platform login" in result.output


def test_rejected_token_asks_for_login_without_leaking_it(api):
  auth.save_credentials({"access_token": "secret-token-value", "refresh_token": "r", "expires_in": 300})
  result = runner.invoke(app, ["whoami"])
  assert result.exit_code == 1
  assert "platform login" in result.output
  assert "secret-token-value" not in result.output


def test_logout_revokes_refresh_token(idp, oidc, monkeypatch):
  auth.save_credentials({"access_token": "a", "refresh_token": "refresh-live", "expires_in": 300})
  monkeypatch.setattr(auth, "Oidc", lambda *a, **k: oidc)
  assert runner.invoke(app, ["logout"]).exit_code == 0
  assert idp.revoked == ["refresh-live"]
  assert not auth.credentials_path().exists()


def test_callback_page_success_in_portuguese():
  page = auth.callback_page(True, None, "pt-BR,pt;q=0.9,en;q=0.8")
  assert '<html lang="pt-BR">' in page
  assert "Você entrou" in page and "Volte para o terminal." in page
  assert '<div class="badge ok"' in page


def test_callback_page_links_to_the_guide():
  page = auth.callback_page(True, None, "en")
  assert f'href="{auth.DOCS_URL}"' in page
  assert "You're signed in" in page


def test_callback_page_failure_escapes_error():
  page = auth.callback_page(False, "<script>alert(1)</script>", "en-US")
  assert "<script>alert(1)</script>" not in page
  assert "&lt;script&gt;" in page
  assert "That didn't work" in page
  assert '<div class="badge fail"' in page


def test_browser_login_serves_themed_page(idp, oidc):
  pages = []
  def open_browser(url):
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    idp.verifiers["code-1"] = query["code_challenge"]
    callback = f"{query['redirect_uri']}?code=code-1&state={query['state']}"
    request = urllib.request.Request(callback, headers={"Accept-Language": "en"})
    threading.Thread(target=lambda: pages.append(urllib.request.urlopen(request).read().decode()), daemon=True).start()
    return True
  oidc.login_browser(open_browser=open_browser, timeout=10)
  time.sleep(0.2)
  assert "You're signed in" in pages[0]


def test_password_login_saves_the_issuing_client(idp):
  oidc = auth.Oidc(issuer=ISSUER, client_id="platform-smoke", transport=httpx.MockTransport(idp.handler))
  auth.save_credentials(oidc.login_password("platform-smoke", "right"), client_id="platform-smoke")
  assert idp.password_logins == [("platform-smoke", "platform-smoke", "right", "openid")]
  assert auth.load_credentials()["client_id"] == "platform-smoke"


def test_password_login_failure_is_clear(idp):
  oidc = auth.Oidc(issuer=ISSUER, client_id="platform-smoke", transport=httpx.MockTransport(idp.handler))
  with pytest.raises(auth.AuthError, match="test user login failed: Invalid user credentials"):
    oidc.login_password("platform-smoke", "wrong")


def test_refresh_uses_the_client_that_issued_the_token(idp):
  auth.save_credentials({"access_token": "old", "refresh_token": "r", "expires_in": 30}, client_id="platform-smoke")
  def factory(client_id=None):
    return auth.Oidc(issuer=ISSUER, client_id=client_id or "platform-cli", transport=httpx.MockTransport(idp.handler))
  assert auth.access_token(oidc_factory=factory) == "access-refreshed"
  assert idp.refresh_clients == ["platform-smoke"]
  # The refreshed credentials keep the client, or the next refresh would go to platform-cli.
  assert auth.load_credentials()["client_id"] == "platform-smoke"


def test_logout_revokes_with_the_issuing_client(idp, monkeypatch):
  auth.save_credentials({"access_token": "a", "refresh_token": "refresh-live", "expires_in": 300}, client_id="platform-smoke")
  monkeypatch.setattr(auth, "Oidc", lambda issuer=None, client_id=None, transport=None: _real_oidc(client_id, idp))
  assert runner.invoke(app, ["logout"]).exit_code == 0
  assert idp.revoke_clients == ["platform-smoke"]


_ORIGINAL_OIDC = auth.Oidc


def _real_oidc(client_id, idp):
  return _ORIGINAL_OIDC(issuer=ISSUER, client_id=client_id or "platform-cli", transport=httpx.MockTransport(idp.handler))


@pytest.fixture
def local_target(config_home):
  from wasp_platform import config
  config.save({"target": "local", "api_url": "http://api.test", "issuer": ISSUER, "client_id": "platform-cli"})


@pytest.mark.parametrize("flags,user", [
  (["--test-user"], "platform-smoke"),
  (["--test-admin"], "platform-smoke-admin"),
])
def test_login_test_user(idp, api, local_target, monkeypatch, flags, user):
  from wasp_platform.bootstrap import local
  monkeypatch.setattr(local, "smoke_password", lambda username: "right" if username == user else "nope")
  monkeypatch.setattr(auth, "Oidc", lambda issuer=None, client_id=None, transport=None: _real_oidc(client_id, idp))
  monkeypatch.setattr(client_module.PlatformClient, "me", lambda self: {"sub": "s", "email": f"{user}@platform.local", "groups": ["platform-users"]})
  result = runner.invoke(app, ["login", *flags])
  assert result.exit_code == 0, result.output
  assert f"Logged in as {user}@platform.local" in result.output
  assert idp.password_logins[0][:2] == ("platform-smoke", user)
  assert auth.load_credentials()["client_id"] == "platform-smoke"


def test_login_test_user_only_on_local(config_home):
  from wasp_platform import config
  config.save({"target": "azure", "api_url": "http://api.test", "issuer": ISSUER, "client_id": "platform-cli"})
  result = runner.invoke(app, ["login", "--test-user"])
  assert result.exit_code == 1
  assert "--test-user is only supported on the local target" in result.output


def test_login_test_flags_are_hidden():
  result = runner.invoke(app, ["login", "--help"])
  assert "--use-device-code" in result.output
  assert "--test-user" not in result.output and "--test-admin" not in result.output


def test_old_credentials_without_client_refresh_with_the_configured_client(idp):
  auth.save_credentials({"access_token": "old", "refresh_token": "r", "expires_in": 30})
  def factory(client_id=None):
    return auth.Oidc(issuer=ISSUER, client_id=client_id or "platform-cli", transport=httpx.MockTransport(idp.handler))
  assert auth.access_token(oidc_factory=factory) == "access-refreshed"
  assert idp.refresh_clients == ["platform-cli"]
  assert "client_id" not in auth.load_credentials()


def test_refresh_now_renews_before_expiry(idp, oidc):
  auth.save_credentials({"access_token": "fresh", "refresh_token": "refresh-old", "expires_in": 300})
  assert auth.refresh_now(oidc_factory=lambda: oidc)["access_token"] == "access-refreshed"
  assert idp.refreshed == 1
  assert auth.load_credentials()["access_token"] == "access-refreshed"


def test_refresh_now_without_refresh_token():
  with pytest.raises(auth.AuthError, match="platform login"):
    auth.refresh_now()
  auth.save_credentials({"access_token": "a", "expires_in": 300})
  with pytest.raises(auth.AuthError, match="platform login"):
    auth.refresh_now()


def me_with_token(monkeypatch):
  """me() answers with the token it was called with, so a test sees which token login used."""
  monkeypatch.setattr(client_module.PlatformClient, "me", lambda self: {"sub": "s", "email": "dev@example.com", "groups": [self.token()]})


def test_login_refresh_renews_without_browser(idp, local_target, monkeypatch):
  auth.save_credentials({"access_token": "old", "refresh_token": "refresh-old", "expires_in": 300}, client_id="platform-smoke")
  monkeypatch.setattr(auth, "Oidc", lambda issuer=None, client_id=None, transport=None: _real_oidc(client_id, idp))
  monkeypatch.setattr(_ORIGINAL_OIDC, "login_browser", lambda self: pytest.fail("no browser with a live refresh token"))
  me_with_token(monkeypatch)
  result = runner.invoke(app, ["login", "--refresh"])
  assert result.exit_code == 0, result.output
  assert "Logged in as dev@example.com (access-refreshed)" in result.output
  assert idp.refresh_clients == ["platform-smoke"]
  assert auth.load_credentials()["client_id"] == "platform-smoke"


@pytest.mark.parametrize("credentials", [None, {"access_token": "a", "refresh_token": "refused", "expires_in": 300}])
def test_login_refresh_falls_back_to_the_browser(idp, local_target, monkeypatch, credentials):
  if credentials:
    auth.save_credentials(credentials)
  real = idp.handler

  def refused(request):
    if b"grant_type=refresh_token" in request.content:
      return httpx.Response(400, json={"error": "invalid_grant"})
    return real(request)

  browser = _ORIGINAL_OIDC(issuer=ISSUER, client_id="platform-cli", transport=httpx.MockTransport(refused))
  browser.login_browser = lambda: {"access_token": "access-browser", "refresh_token": "r", "expires_in": 300}
  monkeypatch.setattr(auth, "Oidc", lambda issuer=None, client_id=None, transport=None: browser)
  me_with_token(monkeypatch)
  result = runner.invoke(app, ["login", "--refresh"])
  assert result.exit_code == 0, result.output
  assert "signing in again" in result.output
  assert "Logged in as dev@example.com (access-browser)" in result.output


def test_login_refresh_with_a_test_flag_is_a_usage_error(config_home):
  result = runner.invoke(app, ["login", "--refresh", "--test-user"])
  assert result.exit_code == 2
  assert "--refresh" in result.output
