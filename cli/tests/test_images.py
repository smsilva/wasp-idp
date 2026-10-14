import json
from pathlib import Path

import pytest

from wasp_platform.bootstrap import local

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


IMAGES = {"platform-api": "platform-api:platform-api-id", "forager-provider": "forager-provider:forager-provider-id"}


def test_builds_every_image(cluster):
  assert local.build_images(BUILDS) == IMAGES
  assert sorted(cluster["built"]) == ["forager-provider", "platform-api"]


def test_imports_every_missing_image_in_one_call(cluster):
  local.import_images(IMAGES, lambda message: None)
  assert cluster["imports"] == [["platform-api:platform-api-id", "forager-provider:forager-provider-id"]]


def test_an_image_the_node_already_has_is_not_imported(cluster):
  cluster["node_images"]["k3d-platform-local-server-0"] = "docker.io/library/platform-api:platform-api-id\ndocker.io/library/traefik:v3\n"
  local.import_images(IMAGES, lambda message: None)
  assert cluster["imports"] == [["forager-provider:forager-provider-id"]]


def test_nothing_to_import_skips_k3d(cluster):
  cluster["node_images"]["k3d-platform-local-server-0"] = "docker.io/library/platform-api:platform-api-id\ndocker.io/library/forager-provider:forager-provider-id\n"
  messages = []
  local.import_images(IMAGES, messages.append)
  assert cluster["imports"] == []
  assert any("already in the cluster" in message for message in messages)


def test_a_failing_build_fails_the_step(cluster, monkeypatch):
  def build(name, context, dockerfile=None):
    raise local.BootstrapError(f"docker build {name} failed")

  monkeypatch.setattr(local, "_build", build)
  with pytest.raises(local.BootstrapError, match="docker build"):
    local.build_images(BUILDS)


def test_providers_never_wait_for_keycloak_or_the_api(tmp_path):
  tasks = {task.name: task for task in local.init_tasks(tmp_path, None, None, lambda message: None)}

  def ancestors(name):
    found = set()
    for need in tasks[name].needs:
      found |= {need} | ancestors(need)
    return found

  for provider in ("local-vcluster-provider", "scm-github-provider", "workload-provider", "forager-provider", "registry-provider"):
    assert not ancestors(provider) & {"keycloak", "platform-api"}, provider
  assert {"keycloak admin permissions", "import images"} <= ancestors("platform-api")
  assert "cluster" not in ancestors("build images")


def test_stop_ends_running_commands_and_refuses_new_ones():
  import threading

  local._stopping.clear()
  errors = []

  def sleeper():
    try:
      local._run("sleep", "30")
    except local.BootstrapError as error:
      errors.append(error)

  thread = threading.Thread(target=sleeper)
  thread.start()
  while not local._processes:
    pass
  local.stop()
  thread.join(5)
  assert not thread.is_alive()
  assert isinstance(errors[0], local.Stopped)
  with pytest.raises(local.Stopped):
    local._run("true")
  local._stopping.clear()
