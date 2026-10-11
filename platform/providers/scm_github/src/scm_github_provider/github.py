"""The slice of the GitHub REST API the controller uses: as the App (RS256 JWT), and as its installation on the org."""
import base64
import time

import httpx
import jwt

API = "https://api.github.com"


class GitHubError(Exception):
  def __init__(self, status: int, message: str, retry_after: float | None = None):
    super().__init__(f"GitHub answered {status}: {message}")
    self.status = status
    # Seconds GitHub asks to wait before the next call; set only for a rate limit.
    self.retry_after = retry_after

  @property
  def rate_limited(self) -> bool:
    return self.retry_after is not None

  @property
  def transient(self) -> bool:
    """Worth trying again later: a rate limit or a GitHub outage. Any other 4xx will not heal by waiting."""
    return self.rate_limited or self.status >= 500


def retry_after(response: httpx.Response) -> float | None:
  """The primary limit sends x-ratelimit-remaining: 0 and the reset epoch; the secondary one, retry-after
  (with a 403 or a 429). A 429 without either still means wait: one minute, as GitHub documents."""
  headers = response.headers
  if response.status_code not in (403, 429):
    return None
  if headers.get("retry-after", "").isdigit():
    return float(headers["retry-after"])
  if headers.get("x-ratelimit-remaining") == "0" and headers.get("x-ratelimit-reset", "").isdigit():
    return max(float(headers["x-ratelimit-reset"]) - time.time(), 0)
  return 60.0 if response.status_code == 429 else None


def app_jwt(app_id: int, private_key: str, now=time.time) -> str:
  """Valid for 10 minutes, the GitHub maximum; issued 60 s in the past against clock drift."""
  issued = int(now()) - 60
  return jwt.encode({"iat": issued, "exp": issued + 600, "iss": str(app_id)}, private_key, algorithm="RS256")


class Client:
  def __init__(self, authorization: str, transport: httpx.BaseTransport | None = None, base_url: str = API):
    self.transport = transport
    self.base_url = base_url
    self.http = httpx.Client(base_url=base_url, timeout=15, transport=transport, headers={
      "Accept": "application/vnd.github+json",
      "Authorization": authorization,
      "X-GitHub-Api-Version": "2022-11-28",
    })

  def _send(self, method: str, path: str, expected: int | tuple[int, ...] = 200, **kwargs):
    response = self.http.request(method, path, **kwargs)
    if response.status_code not in ((expected,) if isinstance(expected, int) else expected):
      try:
        message = response.json().get("message", response.text)
      except ValueError:
        message = response.text
      raise GitHubError(response.status_code, f"{method} {path}: {message}", retry_after(response))
    return response.json()


class GitHubApp(Client):
  def __init__(self, app_id: int, private_key: str, transport: httpx.BaseTransport | None = None, base_url: str = API):
    self.token = app_jwt(app_id, private_key)
    super().__init__(f"Bearer {self.token}", transport, base_url)

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

  def installation(self, installation_id: int) -> "Installation":
    """A client acting as the installation on the org (valid for one hour): what creates repos."""
    return Installation(self.access_token(installation_id)["token"], self.transport, self.base_url)


class Installation(Client):
  """The repo slice of the REST API: create the repo, then the first commit through the Git Data API."""

  def __init__(self, token: str, transport: httpx.BaseTransport | None = None, base_url: str = API):
    super().__init__(f"token {token}", transport, base_url)

  def repo(self, full_name: str) -> dict | None:
    try:
      return self._send("GET", f"/repos/{full_name}")
    except GitHubError as error:
      if error.status == 404:
        return None
      raise

  def create_repo(self, org: str, name: str, private: bool, description: str | None) -> dict:
    # auto_init: the Git Data API refuses an empty repo (409), so the first commit replaces the README one.
    body = {"name": name, "private": private, "auto_init": True}
    if description:
      body["description"] = description
    return self._send("POST", f"/orgs/{org}/repos", expected=201, json=body)

  def head(self, full_name: str, branch: str) -> str | None:
    """The commit sha the branch points to; None while the repo has none (empty, or just created)."""
    try:
      return self._send("GET", f"/repos/{full_name}/git/ref/heads/{branch}")["object"]["sha"]
    except GitHubError as error:
      if error.status in (404, 409):
        return None
      raise

  def commit_message(self, full_name: str, sha: str) -> str:
    return self._send("GET", f"/repos/{full_name}/git/commits/{sha}")["message"]

  def blob(self, full_name: str, content: bytes) -> str:
    body = {"content": base64.b64encode(content).decode(), "encoding": "base64"}
    return self._send("POST", f"/repos/{full_name}/git/blobs", expected=201, json=body)["sha"]

  def tree(self, full_name: str, entries: list[dict]) -> str:
    return self._send("POST", f"/repos/{full_name}/git/trees", expected=201, json={"tree": entries})["sha"]

  def commit(self, full_name: str, message: str, tree: str, parents: list[str]) -> str:
    body = {"message": message, "tree": tree, "parents": parents}
    return self._send("POST", f"/repos/{full_name}/git/commits", expected=201, json=body)["sha"]

  def protect(self, full_name: str, branch: str) -> None:
    """Changes only by pull request, with no approval required: the org may have a single member, who
    cannot approve their own PR (ADR 0017). PUT replaces the whole protection, so it is idempotent."""
    body = {
      "required_status_checks": None,
      "enforce_admins": False,
      "required_pull_request_reviews": {"required_approving_review_count": 0},
      "restrictions": None,
    }
    self._send("PUT", f"/repos/{full_name}/branches/{branch}/protection", json=body)

  def point_branch(self, full_name: str, branch: str, sha: str, exists: bool) -> None:
    if exists:
      self._send("PATCH", f"/repos/{full_name}/git/refs/heads/{branch}", json={"sha": sha, "force": True})
    else:
      self._send("POST", f"/repos/{full_name}/git/refs", expected=201, json={"ref": f"refs/heads/{branch}", "sha": sha})
