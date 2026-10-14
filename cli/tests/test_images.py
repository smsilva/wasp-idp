import json
from pathlib import Path

import pytest

from wasp_platform.bootstrap import local
from wasp_platform.bootstrap.timings import Timings

BUILDS = {"platform-api": (Path("platform"), Path("platform/api/Dockerfile")), "forager-provider": (Path("forager"), None)}
NODES = [
  {"name": "k3d-platform-local-server-0", "role": "server", "runtimeLabels": {"k3d.cluster": "platform-local"}},
  {"name": "k3d-platform-local-serverlb", "role": "loadbalancer", "runtimeLabels": {"k3d.cluster": "platform-local"}},
  {"name": "k3d-other-server-0", "role": "server", "runtimeLabels": {"k3d.cluster": "other"}},
]


@pytest.fixture
def cluster(monkeypatch):
  """Fakes docker and k3d: builds tag each image <name>:<name>-id; node images are what ctr lists."""
  state = {"node_images": {"k3d-platform-local-server-0": ""}, "imports": [], "built": []}

  def run(*command, input=None, capture=True):
    if command[:3] == ("k3d", "node", "list"):
      return json.dumps(NODES)
    if command[:2] == ("docker", "exec"):
      return state["node_images"][command[2]]
    if command[:3] == ("k3d", "image", "import"):
      state["imports"].append(list(command[3:command.index("--cluster")]))
      return ""
    raise AssertionError(command)

  def build(name, context, dockerfile=None):
    state["built"].append(name)
    return f"{name}:{name}-id"

  monkeypatch.setattr(local, "_run", run)
  monkeypatch.setattr(local, "_build", build)
  return state


def test_builds_every_image_and_imports_all_in_one_call(cluster):
  images = local.prepare_images(BUILDS, lambda message: None, Timings())
  assert images == {"platform-api": "platform-api:platform-api-id", "forager-provider": "forager-provider:forager-provider-id"}
  assert sorted(cluster["built"]) == ["forager-provider", "platform-api"]
  assert cluster["imports"] == [["platform-api:platform-api-id", "forager-provider:forager-provider-id"]]


def test_an_image_the_node_already_has_is_not_imported(cluster):
  cluster["node_images"]["k3d-platform-local-server-0"] = "docker.io/library/platform-api:platform-api-id\ndocker.io/library/traefik:v3\n"
  local.prepare_images(BUILDS, lambda message: None, Timings())
  assert cluster["imports"] == [["forager-provider:forager-provider-id"]]


def test_nothing_to_import_skips_k3d(cluster):
  cluster["node_images"]["k3d-platform-local-server-0"] = "docker.io/library/platform-api:platform-api-id\ndocker.io/library/forager-provider:forager-provider-id\n"
  messages = []
  timings = Timings()
  local.prepare_images(BUILDS, messages.append, timings)
  assert cluster["imports"] == []
  assert [name for name, _ in timings.steps] == ["build images (2)", "check images in the cluster"]
  assert any("already in the cluster" in message for message in messages)


def test_a_failing_build_stops_init(cluster, monkeypatch):
  def build(name, context, dockerfile=None):
    raise local.BootstrapError(f"docker build {name} failed")

  monkeypatch.setattr(local, "_build", build)
  with pytest.raises(local.BootstrapError, match="docker build"):
    local.prepare_images(BUILDS, lambda message: None, Timings())
  assert cluster["imports"] == []
