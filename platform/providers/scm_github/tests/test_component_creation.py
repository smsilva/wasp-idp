"""Each step of a ComponentCreation and the resume after a restart, with GitHub simulated by httpx.MockTransport."""
import base64
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from scm_github_provider.component_creation import TRAILER, CreationReconciler, summarize_app_spec
from scm_github_provider.github import GitHubApp
from scm_github_provider.store import AlreadyExists

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
# A throwaway key generated per run: the repo is public, no real App, installation or key here.
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
SEED = Path(__file__).parents[3] / "templates" / "python-service" / "content"
WRITES = ("POST", "PATCH", "PUT", "DELETE")


class FakeGitHub:
  """Repos, blobs, trees, commits and refs in memory, enough for the steps of a creation."""

  def __init__(self):
    self.repos = {}  # full name -> repo
    self.refs = {}  # full name -> sha of main
    self.objects = {}  # sha -> blob, tree or commit
    self.calls = []
    self.fail = {}  # "METHOD /path suffix" -> status, while set

  def _sha(self, value) -> str:
    sha = f"{len(self.objects) + 1:040x}"
    self.objects[sha] = value
    return sha

  def outside(self, full_name):
    """A repo someone created by hand on the org."""
    self.repos[full_name] = {"full_name": full_name, "node_id": "R_other", "html_url": f"https://github.com/{full_name}"}

  def handler(self, request: httpx.Request) -> httpx.Response:
    method, path = request.method, request.url.path
    self.calls.append(f"{method} {path}")
    for key, status in self.fail.items():
      if f"{method} {path}".endswith(key):
        return httpx.Response(status, json={"message": "Server Error"})
    body = json.loads(request.content) if request.content else {}
    if path.endswith("/access_tokens"):
      return httpx.Response(201, json={"token": "ghs_fake"})
    if method == "POST" and path.startswith("/orgs/"):
      org = path.split("/")[2]
      full_name = f"{org}/{body['name']}"
      if full_name in self.repos:
        return httpx.Response(422, json={"message": "Repository creation failed.", "errors": [{"message": "name already exists on this account"}]})
      self.repos[full_name] = {"full_name": full_name, "node_id": f"R_{body['name']}", "html_url": f"https://github.com/{full_name}", "private": body["private"]}
      if body.get("auto_init"):
        self.refs[full_name] = self._sha({"message": "Initial commit", "tree": {}, "parents": []})
      return httpx.Response(201, json=self.repos[full_name])
    parts = path.split("/")
    full_name = "/".join(parts[2:4])
    rest = "/".join(parts[4:])
    if full_name not in self.repos:
      return httpx.Response(404, json={"message": "Not Found"})
    if method == "GET" and rest == "":
      return httpx.Response(200, json=self.repos[full_name])
    if method == "GET" and rest == "git/ref/heads/main":
      if full_name not in self.refs:
        return httpx.Response(409, json={"message": "Git Repository is empty."})
      return httpx.Response(200, json={"object": {"sha": self.refs[full_name]}})
    if method == "GET" and rest.startswith("git/commits/"):
      return httpx.Response(200, json=self.objects[parts[-1]])
    if method == "POST" and rest == "git/blobs":
      return httpx.Response(201, json={"sha": self._sha(base64.b64decode(body["content"]))})
    if method == "POST" and rest == "git/trees":
      return httpx.Response(201, json={"sha": self._sha({entry["path"]: entry for entry in body["tree"]})})
    if method == "POST" and rest == "git/commits":
      return httpx.Response(201, json={"sha": self._sha({"message": body["message"], "tree": body["tree"], "parents": body["parents"]})})
    if method == "PATCH" and rest == "git/refs/heads/main":
      self.refs[full_name] = body["sha"]
      return httpx.Response(200, json={})
    if method == "POST" and rest == "git/refs":
      self.refs[full_name] = body["sha"]
      return httpx.Response(201, json={})
    return httpx.Response(404, json={"message": "Not Found"})

  def factory(self, app_id, key):
    return GitHubApp(app_id, key, transport=httpx.MockTransport(self.handler), base_url="https://api.github.test")

  def files(self, full_name) -> dict[str, bytes]:
    commit = self.objects[self.refs[full_name]]
    return {path: self.objects[entry["sha"]] for path, entry in self.objects[commit["tree"]].items()}

  def writes(self) -> list[str]:
    return [call for call in self.calls if call.split()[0] in WRITES and not call.endswith("/access_tokens")]


class FakeObjects:
  """One plural of CRs: what the reconciler reads and writes."""

  def __init__(self, *objects):
    self.items = {obj["metadata"]["name"]: copy.deepcopy(obj) for obj in objects}
    self.patches = []
    self.version = 0

  def get(self, name):
    return copy.deepcopy(self.items.get(name))

  def patch_status(self, name, status):
    self.patches.append(copy.deepcopy(status))
    self.items[name]["status"] = copy.deepcopy(status)

  def create(self, body):
    if body["metadata"]["name"] in self.items:
      raise AlreadyExists(body["metadata"]["name"])
    self.version += 1
    self.items[body["metadata"]["name"]] = {**copy.deepcopy(body), "metadata": {**body["metadata"], "resourceVersion": str(self.version)}}

  def replace(self, body):
    assert body["metadata"]["resourceVersion"] == self.items[body["metadata"]["name"]]["metadata"]["resourceVersion"]
    self.items[body["metadata"]["name"]] = copy.deepcopy(body)


class FakeSecrets:
  def private_key(self, name):
    return PEM


def connection(ready=True):
  condition = {"type": "Ready", "status": "True", "reason": "Verified"} if ready else {"type": "Ready", "status": "False", "reason": "NotInstalled"}
  return {
    "metadata": {"name": "wasp-foundry"},
    "spec": {"vendor": "github", "github": {"org": "wasp-foundry", "appId": 42, "installationId": 7}, "credentialRef": "scm-wasp-foundry"},
    "status": {"conditions": [condition]},
  }


def creation(prd="# Problem\nGreet people.\n", visibility="public"):
  spec = {
    "system": "greeter", "owner": "team-alpha", "type": "service", "description": "Says hello",
    "template": {"name": "python-service", "default": True, "copyWithoutRendering": [".github/workflows/*"],
                 "source": {"repo": "https://github.com/smsilva/wasp-idp", "path": "platform/templates/python-service/content", "ref": "abc123"}},
    "params": {"port": 9000}, "scmConnection": "wasp-foundry", "visibility": visibility,
  }
  if prd is not None:
    spec["prd"] = prd
  return {"metadata": {"name": "greeting-api", "uid": "uid-1"}, "spec": spec}


class World:
  def __init__(self, tmp_path, obj=None, ready=True):
    self.github = FakeGitHub()
    self.creations = FakeObjects(obj or creation())
    self.connections = FakeObjects(connection(ready))
    self.components = FakeObjects()
    self.tmp_path = tmp_path
    self.fetches = 0
    self.restart()

  def restart(self):
    """A new process: a new reconciler and an empty volume, the CRs as the cluster keeps them."""
    self.workdir = self.tmp_path / f"work-{len(list(self.tmp_path.iterdir()))}"

    def fetch(source, into):
      self.fetches += 1
      return SEED

    self.reconciler = CreationReconciler(
      self.creations, self.connections, self.components, FakeSecrets(), self.workdir,
      github_factory=self.github.factory, fetch_source=fetch, now=lambda: NOW,
    )

  def run(self):
    self.reconciler.reconcile(self.creations.get("greeting-api"))
    return self.creations.get("greeting-api")["status"]


def conditions(status) -> dict:
  return {item["type"]: (item["status"], item["reason"]) for item in status["conditions"]}


@pytest.fixture
def world(tmp_path):
  return World(tmp_path)


def test_every_step_runs_in_order(world):
  status = world.run()
  assert conditions(status) == {
    "Validated": ("True", "Validated"), "Rendered": ("True", "Rendered"), "RepoCreated": ("True", "Created"),
    "Pushed": ("True", "Pushed"), "Registered": ("True", "Registered"), "Ready": ("True", "Created"),
  }
  assert [item["type"] for item in status["conditions"]] == ["Validated", "Rendered", "RepoCreated", "Pushed", "Registered", "Ready"]
  assert status["repo"] == {"fullName": "wasp-foundry/greeting-api", "url": "https://github.com/wasp-foundry/greeting-api", "nodeId": "R_greeting-api"}
  assert world.github.repos["wasp-foundry/greeting-api"]["private"] is False
  # The rendered content leaves the volume once the creation is Ready.
  assert not any(world.workdir.iterdir())


def test_first_commit_replaces_the_readme_with_the_rendered_content(world):
  status = world.run()
  full_name = "wasp-foundry/greeting-api"
  commit = world.github.objects[world.github.refs[full_name]]
  assert commit["parents"] == []
  assert f"{TRAILER}: greeting-api" in commit["message"].splitlines()
  files = world.github.files(full_name)
  assert sorted(files) == status["files"]
  assert files["docs/prd.md"] == b"# Problem\nGreet people.\n"
  catalog = yaml.safe_load(files["catalog-info.yaml"])
  assert catalog["metadata"]["annotations"]["platform.wasp.silvios.me/template"] == "python-service@abc123"
  assert catalog["metadata"]["annotations"]["github.com/project-slug"] == "wasp-foundry/greeting-api"
  assert catalog["spec"]["system"] == "greeter"
  assert b"targetPort: 9000" in files["app-spec.yaml"]
  # copyWithoutRendering: the workflow keeps its own ${{ }} expressions.
  workflow = next(path for path in files if path.startswith(".github/workflows/"))
  assert files[workflow] == (SEED / workflow).read_bytes()
  assert status["appSpec"] == {"containers": ["api"], "resources": ["postgres"], "routes": ["/"]}


def test_without_prd_the_template_skeleton_stays(tmp_path):
  world = World(tmp_path, creation(prd=None, visibility="private"))
  world.run()
  files = world.github.files("wasp-foundry/greeting-api")
  assert files["docs/prd.md"].startswith(b"# greeting-api")  # the skeleton, rendered
  assert world.github.repos["wasp-foundry/greeting-api"]["private"] is True


def test_registered_mirrors_catalog_info(world):
  world.run()
  index = world.components.get("greeting-api")
  assert index["apiVersion"] == "catalog.platform.wasp.silvios.me/v1alpha1"
  assert index["spec"] == {
    "owner": "team-alpha", "system": "greeter", "type": "service", "lifecycle": "experimental",
    "source": {"repo": "wasp-foundry/greeting-api", "template": "python-service@abc123", "origin": "created"},
    "description": "Says hello",
  }


def test_resumes_between_repo_created_and_pushed(world):
  world.github.fail["/git/blobs"] = 502
  status = world.run()
  assert conditions(status)["RepoCreated"] == ("True", "Created")
  assert conditions(status)["Pushed"] == ("False", "GitHubError")
  assert conditions(status)["Ready"] == ("False", "GitHubError")
  assert status["repo"]["nodeId"] == "R_greeting-api"

  # The controller dies: the volume is gone, the CR keeps its status.
  del world.github.fail["/git/blobs"]
  world.restart()
  status = world.run()
  assert conditions(status)["Ready"] == ("True", "Created")
  assert world.github.writes().count("POST /orgs/wasp-foundry/repos") == 1
  assert world.fetches == 2  # rendered again: fixed ref, same content
  assert "docs/prd.md" in world.github.files("wasp-foundry/greeting-api")


def test_a_push_already_done_is_not_repeated(world):
  world.github.fail["/git/refs/heads/main"] = 502
  world.run()  # the commit exists, main still points to the README
  del world.github.fail["/git/refs/heads/main"]
  world.run()
  pushed = world.github.refs["wasp-foundry/greeting-api"]
  blobs = world.github.writes().count("POST /repos/wasp-foundry/greeting-api/git/blobs")

  # Registered fails after Pushed: the next pass finds its own commit on main and writes no blob.
  world.creations.items["greeting-api"]["status"]["conditions"] = [
    item for item in world.creations.items["greeting-api"]["status"]["conditions"] if item["type"] not in ("Registered", "Ready")
  ]
  world.restart()
  world.run()
  assert world.github.refs["wasp-foundry/greeting-api"] == pushed
  assert world.github.writes().count("POST /repos/wasp-foundry/greeting-api/git/blobs") == blobs


def test_a_repo_created_outside_is_never_touched(world):
  world.github.outside("wasp-foundry/greeting-api")
  status = world.run()
  assert conditions(status)["RepoCreated"] == ("False", "RepoAlreadyExists")
  assert conditions(status)["Ready"] == ("False", "RepoAlreadyExists")
  assert world.github.writes() == []
  assert world.components.items == {}


def test_connection_not_ready_stops_at_validated(tmp_path):
  world = World(tmp_path, ready=False)
  status = world.run()
  assert conditions(status) == {"Validated": ("False", "ConnectionNotReady"), "Ready": ("False", "ConnectionNotReady")}
  assert world.github.calls == []


def test_an_unchanged_failure_is_not_written_again(tmp_path):
  world = World(tmp_path, ready=False)
  world.run()
  world.run()
  assert len(world.creations.patches) == 1


def test_component_of_another_repo_is_not_overwritten(world):
  world.components.create({"metadata": {"name": "greeting-api"}, "spec": {"source": {"repo": "elsewhere/greeting-api"}}})
  status = world.run()
  assert conditions(status)["Registered"] == ("False", "ComponentExists")
  assert world.components.get("greeting-api")["spec"]["source"]["repo"] == "elsewhere/greeting-api"


def test_ready_creations_are_left_alone(world):
  world.run()
  calls = len(world.github.calls)
  world.run()
  assert len(world.github.calls) == calls


def test_summarize_app_spec_of_the_seed():
  assert summarize_app_spec((SEED / "app-spec.yaml").read_text()) == {"containers": ["api"], "resources": ["postgres"], "routes": ["/"]}
  assert summarize_app_spec("- not a mapping") == {}
