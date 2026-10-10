"""HTTP client of the Platform API: the only way commands other than init reach the platform."""
import httpx

from . import config


class ApiError(Exception):
  pass


class PlatformClient:
  def __init__(self, base_url: str | None = None, transport: httpx.BaseTransport | None = None):
    base_url = base_url or config.api_url()
    if not base_url:
      raise ApiError("no Platform API configured: run 'platform init --target local' first")
    self.http = httpx.Client(base_url=base_url, timeout=30, transport=transport)

  def _request(self, method: str, path: str, **kwargs) -> dict:
    try:
      response = self.http.request(method, path, **kwargs)
    except httpx.TransportError as error:
      raise ApiError(f"Platform API unreachable at {self.http.base_url}: {error}") from error
    if response.is_error:
      raise ApiError(_detail(response))
    return response.json()

  def create_environment(self, name: str, profile: str, expires: str | None) -> dict:
    return self._request("POST", "/v1/environments", json={"name": name, "profile": profile, "expires": expires})

  def list_environments(self) -> list[dict]:
    return self._request("GET", "/v1/environments")["items"]

  def get_environment(self, name: str) -> dict:
    return self._request("GET", f"/v1/environments/{name}")

  def delete_environment(self, name: str) -> dict:
    return self._request("DELETE", f"/v1/environments/{name}")


def _detail(response: httpx.Response) -> str:
  try:
    detail = response.json().get("detail")
  except ValueError:
    detail = None
  if isinstance(detail, list):  # FastAPI validation errors
    detail = "; ".join(f"{'.'.join(str(p) for p in item['loc'][1:])}: {item['msg']}" for item in detail)
  return f"{response.status_code}: {detail or response.text}"
