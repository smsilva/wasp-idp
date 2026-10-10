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
      return self.tokens("refreshed")
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
  assert "Volte ao terminal." in page and "platform whoami" in page


def test_callback_page_failure_escapes_error():
  page = auth.callback_page(False, "<script>alert(1)</script>", "en-US")
  assert "<script>alert(1)</script>" not in page
  assert "&lt;script&gt;" in page
  assert "Login not completed" in page


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
  assert "Back to the terminal." in pages[0]
