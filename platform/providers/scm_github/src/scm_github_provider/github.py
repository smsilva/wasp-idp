"""The slice of the GitHub REST API the controller uses, authenticated as the App (RS256 JWT)."""
import time

import httpx
import jwt

API = "https://api.github.com"


class GitHubError(Exception):
  def __init__(self, status: int, message: str):
    super().__init__(f"GitHub answered {status}: {message}")
    self.status = status


def app_jwt(app_id: int, private_key: str, now=time.time) -> str:
  """Valid for 10 minutes, the GitHub maximum; issued 60 s in the past against clock drift."""
  issued = int(now()) - 60
  return jwt.encode({"iat": issued, "exp": issued + 600, "iss": str(app_id)}, private_key, algorithm="RS256")


class GitHubApp:
  def __init__(self, app_id: int, private_key: str, transport: httpx.BaseTransport | None = None, base_url: str = API):
    self.token = app_jwt(app_id, private_key)
    self.http = httpx.Client(base_url=base_url, timeout=15, transport=transport, headers={
      "Accept": "application/vnd.github+json",
      "Authorization": f"Bearer {self.token}",
      "X-GitHub-Api-Version": "2022-11-28",
    })

  def _send(self, method: str, path: str, expected: int = 200, **kwargs):
    response = self.http.request(method, path, **kwargs)
    if response.status_code != expected:
      try:
        message = response.json().get("message", response.text)
      except ValueError:
        message = response.text
      raise GitHubError(response.status_code, f"{method} {path}: {message}")
    return response.json()

  def app(self) -> dict:
    return self._send("GET", "/app")

  def installations(self) -> list[dict]:
    found, page = [], 1
    while True:
      batch = self._send("GET", "/app/installations", params={"per_page": 100, "page": page})
      found += batch
      if len(batch) < 100:
        return found
      page += 1

  def access_token(self, installation_id: int) -> dict:
    return self._send("POST", f"/app/installations/{installation_id}/access_tokens", expected=201)
