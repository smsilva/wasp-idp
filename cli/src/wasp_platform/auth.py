"""OIDC login against the platform Keycloak (ADR 0021): PKCE in the browser or the device grant.

Tokens live in ~/.config/platform/credentials (0600). They are never printed or logged.
"""
import base64
import hashlib
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


def save_credentials(tokens: dict) -> None:
  now = time.time()
  values = {
    "access_token": tokens["access_token"],
    "refresh_token": tokens.get("refresh_token"),
    "expires_at": now + int(tokens.get("expires_in", 0)),
  }
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
    callback = _Callback(state)
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
    url = f"{self.endpoint('authorization_endpoint')}?{urllib.parse.urlencode(params)}"
    if not open_browser(url):
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
  if not credentials.get("refresh_token"):
    raise AuthError("session expired: run 'platform login'")
  tokens = oidc_factory().refresh(credentials["refresh_token"])
  save_credentials(tokens)
  return tokens["access_token"]


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


class _Callback:
  """Single-request HTTP listener on a random free port of 127.0.0.1."""

  def __init__(self, state: str):
    self.state = state
    self.code = None
    self.error = None
    self.done = threading.Event()
    owner = self

    class Handler(http.server.BaseHTTPRequestHandler):
      def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if query.get("state", [None])[0] != owner.state:
          owner.error = "state mismatch"
        elif "error" in query:
          owner.error = query.get("error_description", query["error"])[0]
        else:
          owner.code = query.get("code", [None])[0]
        ok = owner.code is not None
        body = ("Login complete. You can return to the terminal." if ok else f"Login failed: {owner.error}").encode()
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)
        owner.done.set()

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
