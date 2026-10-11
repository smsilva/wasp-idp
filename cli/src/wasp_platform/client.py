"""HTTP client of the Platform API: the only way commands other than init reach the platform."""
from urllib.parse import quote

import httpx

from . import auth, config


class ApiError(Exception):
  def __init__(self, message: str, plan: dict | None = None):
    super().__init__(message)
    # The catalog import answers 409/422 with the plan, so the CLI can show what happened.
    self.plan = plan


class PlatformClient:
  def __init__(self, base_url: str | None = None, transport: httpx.BaseTransport | None = None, token=None):
    base_url = base_url or config.api_url()
    if not base_url:
      raise ApiError("no Platform API configured: run 'platform init --target local' first")
    self.http = httpx.Client(base_url=base_url, timeout=30, transport=transport)
    self.token = token or auth.access_token

  def _request(self, method: str, path: str, **kwargs) -> dict:
    try:
      headers = {"Authorization": f"Bearer {self.token()}"}
    except auth.AuthError as error:
      raise ApiError(str(error)) from error
    try:
      response = self.http.request(method, path, headers=headers, **kwargs)
    except httpx.TransportError as error:
      raise ApiError(f"Platform API unreachable at {self.http.base_url}: {error}") from error
    if response.status_code == 401:
      raise ApiError("not authenticated: run 'platform login'")
    if response.is_error:
      raise ApiError(_detail(response), plan=_plan(response))
    # 204 (delete) has no body.
    return response.json() if response.content else {}

  def me(self) -> dict:
    return self._request("GET", "/v1/me")

  def create_environment(self, name: str, profile: str, expires: str | None, shared_with: list[str] | None = None) -> dict:
    body = {"name": name, "profile": profile, "expires": expires}
    if shared_with:
      body["sharedWith"] = shared_with
    return self._request("POST", "/v1/environments", json=body)

  def list_environments(self, all: bool = False) -> list[dict]:
    return self._request("GET", "/v1/environments", params={"all": "true"} if all else None)["items"]

  def share_environment(self, name: str, team: str) -> dict:
    return self._request("PUT", f"/v1/environments/{name}/shares/{team}")

  def unshare_environment(self, name: str, team: str) -> dict:
    return self._request("DELETE", f"/v1/environments/{name}/shares/{team}")

  def get_environment(self, name: str) -> dict:
    return self._request("GET", f"/v1/environments/{name}")

  def delete_environment(self, name: str) -> dict:
    return self._request("DELETE", f"/v1/environments/{name}")

  def create_catalog_entity(self, plural: str, body: dict) -> dict:
    return self._request("POST", f"/v1/catalog/{plural}", json=body)

  def list_catalog(self, plural: str) -> list[dict]:
    return self._request("GET", f"/v1/catalog/{plural}")["items"]

  def get_catalog_entity(self, plural: str, name: str) -> dict:
    return self._request("GET", f"/v1/catalog/{plural}/{name}")

  def delete_catalog_entity(self, plural: str, name: str) -> None:
    self._request("DELETE", f"/v1/catalog/{plural}/{name}")

  def list_catalog_entities(self, kind: str | None = None, owner: str | None = None) -> list[dict]:
    params = {key: value for key, value in {"kind": kind, "owner": owner}.items() if value}
    return self._request("GET", "/v1/catalog/entities", params=params)["items"]

  def list_teams(self) -> list[dict]:
    return self._request("GET", "/v1/teams")["items"]

  def get_team(self, name: str) -> dict:
    return self._request("GET", f"/v1/teams/{name}")

  def create_team(self, name: str) -> dict:
    return self._request("POST", "/v1/teams", json={"name": name})

  def delete_team(self, name: str) -> None:
    self._request("DELETE", f"/v1/teams/{name}")

  def add_team_member(self, name: str, email: str) -> dict:
    return self._request("POST", f"/v1/teams/{name}/members", json={"email": email})

  def remove_team_member(self, name: str, email: str) -> None:
    self._request("DELETE", f"/v1/teams/{name}/members/{quote(email, safe='@')}")

  def import_catalog(self, documents: list[dict], dry_run: bool, plan_hash: str | None = None) -> dict:
    return self._request("POST", "/v1/catalog/import", json={"documents": documents, "dryRun": dry_run, "planHash": plan_hash})


def _detail(response: httpx.Response) -> str:
  """The API answers every error as {"error": {"code", "message"}}."""
  try:
    message = (response.json().get("error") or {}).get("message")
  except (ValueError, AttributeError):
    message = None
  return f"{response.status_code}: {message or response.text}"


def _plan(response: httpx.Response) -> dict | None:
  try:
    return (response.json().get("error") or {}).get("plan")
  except (ValueError, AttributeError):
    return None
