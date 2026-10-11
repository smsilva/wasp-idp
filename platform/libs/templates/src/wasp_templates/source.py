"""Where a registered template's content comes from, and the values it is rendered with."""
import re
import subprocess
from pathlib import Path

# The same rules as the Platform API (platform_api/templates.py): a Template CR written straight to
# the cluster skips the API, and these values reach git on the machine of whoever renders.
REPO_URL = re.compile(r"^https://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9._~-]+)+$")
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


class SourceError(Exception):
  pass


def _git(*args: str) -> None:
  try:
    subprocess.run(["git", *args], check=True, capture_output=True, text=True)
  except FileNotFoundError:
    raise SourceError("'git' not found in PATH")
  except subprocess.CalledProcessError as error:
    command = next((arg for arg in args if arg in ("init", "fetch", "checkout")), args[0])
    raise SourceError(f"git {command} failed: {(error.stderr or error.stdout).strip()}")


def check(source: dict, allow_local: bool = False) -> None:
  repo, path, ref = source.get("repo") or "", source.get("path") or "", source.get("ref") or ""
  if not REPO_URL.fullmatch(repo) and not (allow_local and repo.startswith("file:///")):
    raise SourceError(f"repo: an https URL of a Git repository, got '{repo}'")
  if not REF.fullmatch(ref) or ".." in ref:
    raise SourceError(f"ref: a tag, branch or commit, got '{ref}'")
  if not path.strip() or path.startswith("/") or ".." in path.split("/") or "\\" in path:
    raise SourceError(f"path: a folder relative to the repo root, without '..', got '{path}'")


def fetch(source: dict, into: Path, allow_local: bool = False) -> Path:
  """The content folder at the registered ref: a shallow fetch of that ref, then a checkout.
  allow_local (tests only) accepts file:// repos."""
  check(source, allow_local)
  repo = into / "repo"
  protocols = ["-c", "protocol.allow=never", "-c", f"protocol.{'file' if allow_local else 'https'}.allow=always"]
  _git("init", "--quiet", str(repo))
  _git(*protocols, "-C", str(repo), "fetch", "--quiet", "--depth", "1", "--", source["repo"], source["ref"])
  _git("-C", str(repo), "checkout", "--quiet", "FETCH_HEAD")
  content = (repo / source["path"]).resolve()
  if not content.is_relative_to(repo.resolve()):
    raise SourceError(f"{source['path']}: leads outside the repo (a symlink)")
  if not content.is_dir():
    raise SourceError(f"{source['path']}: not in {source['repo']} at {source['ref']}")
  return content


def _cast(name: str, schema: dict, value):
  kind = schema.get("type")
  if not isinstance(value, str):
    return value
  if kind == "integer":
    try:
      return int(value)
    except ValueError:
      raise SourceError(f"{name}: '{value}' is not an integer")
  if kind == "number":
    try:
      return float(value)
    except ValueError:
      raise SourceError(f"{name}: '{value}' is not a number")
  if kind == "boolean":
    if value.lower() not in ("true", "false"):
      raise SourceError(f"{name}: '{value}' is not true or false")
    return value.lower() == "true"
  return value


def coerce(schema: dict, given: dict, template: str) -> dict:
  """The extra parameters: defaults from the schema, --param values cast to the declared type."""
  properties = (schema or {}).get("properties") or {}
  unknown = sorted(set(given) - set(properties))
  if unknown:
    raise SourceError(f"{', '.join(unknown)}: not a parameter of {template} ({', '.join(properties) or 'it declares none'})")
  values = {}
  for name, property_schema in properties.items():
    if name in given:
      value = _cast(name, property_schema, given[name])
    elif "default" in property_schema:
      value = property_schema["default"]
    elif name in (schema.get("required") or []):
      raise SourceError(f"{name}: required, pass --param {name}=…")
    else:
      continue
    if "enum" in property_schema and value not in property_schema["enum"]:
      raise SourceError(f"{name}: '{value}' is not one of {', '.join(map(str, property_schema['enum']))}")
    values[name] = value
  return values
