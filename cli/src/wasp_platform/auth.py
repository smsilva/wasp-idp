"""OIDC login against the platform Keycloak (ADR 0021): PKCE in the browser or the device grant.

Tokens live in ~/.config/platform/credentials (0600). They are never printed or logged.
"""
import base64
import hashlib
import html
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import httpx

from . import config

REFRESH_MARGIN = 60  # seconds: renew the access token when it expires sooner than this


class AuthError(Exception):
  pass


def credentials_path() -> Path:
  return config.config_dir() / "credentials"


def load_credentials() -> dict | None:
  path = credentials_path()
  if not path.exists():
    return None
  return json.loads(path.read_text())


def save_credentials(tokens: dict, client_id: str | None = None) -> None:
  """client_id: the client that issued the tokens, when not the configured one (the test client of
  `login --test-user`); refresh and revoke must go to the same client, or Keycloak refuses them."""
  now = time.time()
  values = {
    "access_token": tokens["access_token"],
    "refresh_token": tokens.get("refresh_token"),
    "expires_at": now + int(tokens.get("expires_in", 0)),
  }
  if client_id:
    values["client_id"] = client_id
  path = credentials_path()
  path.parent.mkdir(parents=True, exist_ok=True)
  # Created 0600 from the start: no window where another user could read it.
  descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
  with os.fdopen(descriptor, "w") as file:
    json.dump(values, file)
  os.chmod(path, 0o600)


def delete_credentials() -> None:
  credentials_path().unlink(missing_ok=True)


class Oidc:
  def __init__(self, issuer: str | None = None, client_id: str | None = None, transport: httpx.BaseTransport | None = None):
    settings = config.load()
    self.issuer = issuer or settings.get("issuer")
    self.client_id = client_id or settings.get("client_id")
    # `locale` in the config (en or pt-BR) picks the language of the sign-in pages; without it, the browser's.
    self.locale = settings.get("locale")
    if not (self.issuer and self.client_id):
      raise AuthError("no identity provider configured: run 'platform init --target local' first")
    self.http = httpx.Client(timeout=30, transport=transport)
    self._discovery = None

  def endpoint(self, name: str) -> str:
    if self._discovery is None:
      try:
        response = self.http.get(f"{self.issuer}/.well-known/openid-configuration")
      except httpx.TransportError as error:
        raise AuthError(f"identity provider unreachable at {self.issuer}: {error}") from error
      if response.is_error:
        raise AuthError(f"identity provider discovery failed: {response.status_code}")
      self._discovery = response.json()
    return self._discovery[name]

  def _token(self, data: dict) -> httpx.Response:
    try:
      return self.http.post(self.endpoint("token_endpoint"), data={"client_id": self.client_id, **data})
    except httpx.TransportError as error:
      raise AuthError(f"identity provider unreachable: {error}") from error

  # Authorization Code + PKCE, with a one-shot listener on 127.0.0.1.
  def login_browser(self, open_browser=webbrowser.open, idp_hint: str | None = "google", timeout: int = 300) -> dict:
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(24)
    callback = _Callback(state, self.locale)
    redirect_uri = f"http://127.0.0.1:{callback.port}/callback"
    params = {
      "client_id": self.client_id,
      "response_type": "code",
      "scope": "openid",
      "redirect_uri": redirect_uri,
      "code_challenge": challenge,
      "code_challenge_method": "S256",
      "state": state,
    }
    if idp_hint:
      params["kc_idp_hint"] = idp_hint  # skip the Keycloak page and go straight to Google
    if self.locale:
      params["ui_locales"] = self.locale
    url = f"{self.endpoint('authorization_endpoint')}?{urllib.parse.urlencode(params)}"
    callback.authorize_url = url
    if not open_browser(f"http://127.0.0.1:{callback.port}{callback.start_path}"):
      print(f"Open this URL to sign in:\n{url}")
    code = callback.wait(timeout)
    response = self._token({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier})
    if response.is_error:
      raise AuthError(f"token exchange failed: {_oauth_error(response)}")
    return response.json()

  # Device Authorization Grant (RFC 8628): for SSH sessions, containers, machines without a browser.
  def login_device(self, show, open_browser=webbrowser.open, sleep=time.sleep) -> dict:
    # The client enforces PKCE, and Keycloak applies it to the device grant too.
    verifier, challenge = _pkce()
    data = {"client_id": self.client_id, "scope": "openid", "code_challenge": challenge, "code_challenge_method": "S256"}
    try:
      response = self.http.post(self.endpoint("device_authorization_endpoint"), data=data)
    except httpx.TransportError as error:
      raise AuthError(f"identity provider unreachable: {error}") from error
    if response.is_error:
      raise AuthError(f"device authorization failed: {_oauth_error(response)}")
    device = response.json()
    show(device["user_code"], device.get("verification_uri_complete") or device["verification_uri"])
    if device.get("verification_uri_complete"):
      open_browser(device["verification_uri_complete"])
    interval = int(device.get("interval", 5))
    deadline = time.monotonic() + int(device.get("expires_in", 600))
    while time.monotonic() < deadline:
      sleep(interval)
      response = self._token({"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": device["device_code"], "code_verifier": verifier})
      if response.is_success:
        return response.json()
      error = response.json().get("error")
      if error == "authorization_pending":
        continue
      if error == "slow_down":
        interval += 5
        continue
      raise AuthError(f"device login failed: {error}")
    raise AuthError("device login expired: run 'platform login --use-device-code' again")

  def login_password(self, username: str, password: str) -> dict:
    """Password grant: only the local test client allows it (realm-smoke.yaml, #179)."""
    response = self._token({"grant_type": "password", "username": username, "password": password, "scope": "openid"})
    if response.is_error:
      raise AuthError(f"test user login failed: {_oauth_error(response)}")
    return response.json()

  def refresh(self, refresh_token: str) -> dict:
    response = self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})
    if response.is_error:
      raise AuthError("session expired: run 'platform login'")
    return response.json()

  def revoke(self, refresh_token: str) -> None:
    try:
      self.http.post(self.endpoint("revocation_endpoint"), data={"client_id": self.client_id, "token": refresh_token, "token_type_hint": "refresh_token"})
    except (httpx.TransportError, AuthError, KeyError):
      pass  # logout still removes the local credentials


def access_token(oidc_factory=Oidc) -> str:
  """A valid access token, refreshed when it expires within REFRESH_MARGIN seconds."""
  credentials = load_credentials()
  if not credentials:
    raise AuthError("not logged in: run 'platform login'")
  if credentials["expires_at"] - time.time() > REFRESH_MARGIN:
    return credentials["access_token"]
  return refresh_now(oidc_factory)["access_token"]


def refresh_now(oidc_factory=None) -> dict:
  """A new token from the refresh token, even if the current one is still valid: Keycloak reads the
  groups again, so a team joined after the last token shows at once (`login --refresh`)."""
  credentials = load_credentials()
  if not credentials:
    raise AuthError("not logged in: run 'platform login'")
  if not credentials.get("refresh_token"):
    raise AuthError("session expired: run 'platform login'")
  client_id = credentials.get("client_id")
  factory = oidc_factory or Oidc  # resolved at call time, so a patched Oidc applies
  oidc = factory(client_id=client_id) if client_id else factory()
  tokens = oidc.refresh(credentials["refresh_token"])
  save_credentials(tokens, client_id)
  return tokens


def _pkce() -> tuple[str, str]:
  verifier = secrets.token_urlsafe(64)
  challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
  return verifier, challenge


def _oauth_error(response: httpx.Response) -> str:
  try:
    body = response.json()
    return body.get("error_description") or body.get("error") or str(response.status_code)
  except ValueError:
    return str(response.status_code)


# The guide the page links to, under the card.
DOCS_URL = "https://smsilva.github.io/wasp-idp/platform/"

CALLBACK_TEXT = {
  "en": {
    "ok": ("You're signed in", "Return to the terminal. You can close this tab."),
    "fail": ("That didn't work", "Run platform login again."),
    "start": ("Opening sign-in…", "Taking you to the sign-in page.", "Continue"),
    "docs": "Documentation",
  },
  "pt-BR": {
    "ok": ("Você entrou", "Volte para o terminal. Pode fechar esta aba."),
    "fail": ("Não deu certo", "Rode platform login de novo."),
    "start": ("Abrindo o login…", "Levando você para a página de login.", "Continuar"),
    "docs": "Documentação",
  },
}


def _language(accept_language: str, locale: str | None = None) -> str:
  """The configured locale wins over the browser's Accept-Language."""
  return "pt-BR" if (locale or accept_language).lower().startswith("pt") else "en"


def _page(lang: str, state: str, heading: str, message: str, error: str = "", refresh: str = "", under: str = "") -> str:
  template = (Path(__file__).parent / "assets" / "callback.html").read_text()
  return template.format(
    lang=lang, title=heading, heading=heading, message=message, error=error, refresh=refresh, under=under,
    state=state, mark={"ok": "✓", "fail": "✗"}.get(state, ""),
  )


def callback_page(ok: bool, error: str | None, accept_language: str = "", locale: str | None = None) -> str:
  """The browser page at the end of `platform login` (#537): one card with the outcome, like the Keycloak screens."""
  lang = _language(accept_language, locale)
  text = CALLBACK_TEXT[lang]
  heading, message = text["ok" if ok else "fail"]
  # The error comes from the redirect query string: escape it, an attacker controls it.
  detail = "" if ok else html.escape(error) if error else "login failed"
  under = f'<div class="under"><a href="{DOCS_URL}" target="_blank" rel="noopener">{text["docs"]}</a></div>'
  return _page(lang, "ok" if ok else "fail", heading, message, error=detail, under=under)


def start_page(url: str, accept_language: str = "", locale: str | None = None) -> str:
  """The first page `platform login` opens (#537): the card, painted at once, while the browser goes on to Keycloak.
  Without it the tab stays blank until Keycloak and Google answer."""
  lang = _language(accept_language, locale)
  heading, message, button = CALLBACK_TEXT[lang]["start"]
  target = html.escape(url, quote=True)
  # Two frames first so the card is painted, then on to Keycloak; the browser keeps it on screen until Keycloak
  # answers. replace() keeps /start out of the history. The meta refresh covers a tab without JavaScript.
  refresh = f'<meta http-equiv="refresh" content="1;url={target}">\n'
  under = (
    f'<div class="under"><a id="go" href="{target}">{button}</a></div>\n'
    "<script>requestAnimationFrame(() => requestAnimationFrame(() => location.replace(document.getElementById('go').href)));</script>"
  )
  return _page(lang, "wait", heading, message, refresh=refresh, under=under)


class _Callback:
  """Single-request HTTP listener on a random free port of 127.0.0.1."""

  def __init__(self, state: str, locale: str | None = None):
    self.state = state
    self.locale = locale
    self.authorize_url = ""  # what the start page sends the browser on to
    # The start page carries the state: an unguessable path, served once, so a page in another tab can't read it.
    self.start_path = f"/start/{secrets.token_urlsafe(16)}"
    self.code = None
    self.error = None
    self.done = threading.Event()
    owner = self

    class Handler(http.server.BaseHTTPRequestHandler):
      def do_GET(self):
        # DNS rebinding: a hostile site resolved to 127.0.0.1 sends its own name as Host.
        if self.headers.get("Host") != f"127.0.0.1:{owner.port}":
          self._send(403, "")
          return
        url = urllib.parse.urlparse(self.path)
        if url.path == owner.start_path and owner.authorize_url:
          authorize_url, owner.authorize_url = owner.authorize_url, ""
          self._send(200, start_page(authorize_url, self.headers.get("Accept-Language", ""), owner.locale))
          return
        if url.path != "/callback":
          self._send(404, "")
          return
        query = urllib.parse.parse_qs(url.query)
        if query.get("state", [None])[0] != owner.state:
          owner.error = "state mismatch"
        elif "error" in query:
          owner.error = query.get("error_description", query["error"])[0]
        else:
          owner.code = query.get("code", [None])[0]
        ok = owner.code is not None
        self._send(200 if ok else 400, callback_page(ok, owner.error, self.headers.get("Accept-Language", ""), owner.locale))
        owner.done.set()

      def _send(self, status: int, page: str):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode())

      def log_message(self, *args):
        pass  # the query string carries the authorization code

    self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    self.server.timeout = 1  # handle_request returns every second so the loop can stop
    self.port = self.server.server_address[1]
    threading.Thread(target=self._serve, daemon=True).start()

  def _serve(self):
    while not self.done.is_set():
      self.server.handle_request()

  def wait(self, timeout: int) -> str:
    finished = self.done.wait(timeout)
    self.server.server_close()
    if not finished:
      raise AuthError("login timed out waiting for the browser")
    if self.error or not self.code:
      raise AuthError(f"login failed: {self.error or 'no authorization code'}")
    return self.code
