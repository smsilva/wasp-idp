import json
import subprocess
from pathlib import Path

import pytest
import yaml

from wasp_platform.bootstrap import local
from wasp_platform.bootstrap.tasks import reporting

BUILDS = {"platform-api": (Path("platform"), Path("platform/api/Dockerfile")), "forager-provider": (Path("forager"), None)}
NODES = [
  {"name": "k3d-platform-local-server-0", "role": "server", "runtimeLabels": {"k3d.cluster": "platform-local"}},
  {"name": "k3d-platform-local-serverlb", "role": "loadbalancer", "runtimeLabels": {"k3d.cluster": "platform-local"}},
  # k3d lists its tools node without a role key (seen on macOS with Colima, #547).
  {"name": "k3d-platform-local-tools", "runtimeLabels": {"k3d.cluster": "platform-local"}},
  {"name": "k3d-other-server-0", "role": "server", "runtimeLabels": {"k3d.cluster": "other"}},
]


@pytest.fixture
def cluster(monkeypatch):
  """Fakes docker and k3d: builds tag each image <name>:<name>-id; node images are what ctr lists."""
  state = {"node_images": {"k3d-platform-local-server-0": ""}, "imports": [], "built": []}

  def run(*command, input=None, secret=False):
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
  local.import_images(IMAGES)
  assert cluster["imports"] == [["platform-api:platform-api-id", "forager-provider:forager-provider-id"]]


def test_an_image_the_node_already_has_is_not_imported(cluster):
  cluster["node_images"]["k3d-platform-local-server-0"] = "docker.io/library/platform-api:platform-api-id\ndocker.io/library/traefik:v3\n"
  local.import_images(IMAGES)
  assert cluster["imports"] == [["forager-provider:forager-provider-id"]]


def test_nothing_to_import_skips_k3d(cluster, recorder):
  cluster["node_images"]["k3d-platform-local-server-0"] = "docker.io/library/platform-api:platform-api-id\ndocker.io/library/forager-provider:forager-provider-id\n"
  with reporting("import images", recorder):
    local.import_images(IMAGES)
  assert cluster["imports"] == []
  assert any(event[0] == "note" and "already in the cluster" in event[2] for event in recorder.events)


def test_a_failing_build_fails_the_step(cluster, monkeypatch):
  def build(name, context, dockerfile=None):
    raise local.BootstrapError(f"docker build {name} failed")

  monkeypatch.setattr(local, "_build", build)
  with pytest.raises(local.BootstrapError, match="docker build"):
    local.build_images(BUILDS)


def test_providers_never_wait_for_keycloak_or_the_api(tmp_path):
  tasks = {task.name: task for task in local.init_tasks(tmp_path, None, None)}

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


def test_a_command_reaches_the_log_of_its_step_line_by_line(recorder):
  local._stopping.clear()
  with reporting("keycloak", recorder):
    stdout = local._run("sh", "-c", "echo one; echo two >&2; cat", input="three\n")
  assert stdout == "one\nthree\n"
  events = recorder.of("keycloak")
  assert events[0] == ("command", "keycloak", ("sh", "-c", "echo one; echo two >&2; cat"))
  assert {event[2] for event in events if event[0] == "output"} == {"one", "two", "three"}
  assert events[-1] == ("exited", "keycloak", 0)


def test_a_secret_command_keeps_its_output_out_of_the_log(recorder):
  local._stopping.clear()
  with reporting("keycloak", recorder):
    assert local._run("echo", "c2VjcmV0", secret=True) == "c2VjcmV0\n"
  assert [event[0] for event in recorder.of("keycloak")] == ["command", "exited"]


def test_a_failing_command_keeps_its_stderr_in_the_error(recorder):
  local._stopping.clear()
  with reporting("traefik", recorder), pytest.raises(local.BootstrapError, match="no such deployment"):
    local._run("sh", "-c", "echo no such deployment >&2; exit 3")
  assert recorder.of("traefik")[-1] == ("exited", "traefik", 3)


def test_each_parallel_build_reports_to_the_build_step(monkeypatch, recorder):
  monkeypatch.setattr(local, "_build", lambda name, context, dockerfile=None: (local.note(f"built {name}"), name)[1])
  with reporting("build images", recorder):
    local.build_images(BUILDS)
  assert sorted(event[2] for event in recorder.of("build images")) == ["built forager-provider", "built platform-api"]


def test_render_calls_helm_template_show_only(monkeypatch):
  calls = []

  def run(*command, input=None, secret=False):
    calls.append(command)
    return "apiVersion: v1\nkind: ServiceAccount\n"

  monkeypatch.setattr(local, "_run", run)
  root = Path("/repo")
  manifest = local._render(root, "templates/providers/registry-provider.yaml", {"images.registryProvider.tag": "abc123"})
  assert manifest == "apiVersion: v1\nkind: ServiceAccount\n"
  assert calls == [(
    "helm", "template", "platform-control-plane", str(root / "platform" / "chart" / "platform-control-plane"),
    "--show-only", "templates/providers/registry-provider.yaml",
    "--set", "images.registryProvider.tag=abc123",
  )]


def test_render_with_no_set_values(monkeypatch):
  calls = []
  monkeypatch.setattr(local, "_run", lambda *command, input=None, secret=False: calls.append(command) or "rendered\n")
  local._render(Path("/repo"), "templates/keycloak/keycloak.yaml")
  assert calls == [(
    "helm", "template", "platform-control-plane", str(Path("/repo") / "platform" / "chart" / "platform-control-plane"),
    "--show-only", "templates/keycloak/keycloak.yaml",
  )]


def test_render_propagates_failure_on_a_bad_template_path(monkeypatch):
  """`helm template --show-only` on a path the chart does not have exits non-zero; `_run` already turns
  that into a BootstrapError (local.py:133) — `_render` must not swallow it into an empty manifest."""
  def run(*command, input=None, secret=False):
    raise local.BootstrapError("helm template … failed:\ncould not find template templates/providers/regsitry-provider.yaml in chart")

  monkeypatch.setattr(local, "_run", run)
  with pytest.raises(local.BootstrapError, match="regsitry-provider"):
    local._render(Path("/repo"), "templates/providers/regsitry-provider.yaml")


# Every template of platform-control-plane and the object count (`kind:` documents) it must render,
# counted against the original (now doc-only) deploy/*.yaml manifests of #599: a future edit that drops an
# object from a template fails this test immediately instead of silently diverging from history. The two
# providers that render nothing unless their feature is enabled (ADR 0029, ADR 0032) are rendered with
# that flag set, matching how `_deploy` enables them (local.py's CHART_TEMPLATES/_deploy).
CHART_TEMPLATE_OBJECT_COUNTS = {
  "templates/api/platform-api.yaml": (9, {}),
  "templates/providers/local-vcluster-provider.yaml": (3, {}),
  "templates/providers/scm-github-provider.yaml": (4, {}),
  "templates/providers/workload-provider.yaml": (4, {}),
  "templates/providers/forager-provider.yaml": (8, {}),
  "templates/providers/registry-provider.yaml": (4, {}),
  "templates/providers/aws-account-provider.yaml": (4, {"providers.awsAccount.enabled": "true"}),
  "templates/providers/crossplane-aws-provider.yaml": (6, {"providers.crossplaneAws.enabled": "true"}),
  "templates/keycloak/keycloak.yaml": (4, {}),
  "templates/keycloak/realm-import.yaml": (1, {}),
  "templates/providers/pod-security.yaml": (2, {}),
  "templates/providers/traefik.yaml": (1, {}),
  "templates/providers/crossplane.yaml": (1, {"providers.crossplaneAws.enabled": "true"}),
  "templates/providers/provider-aws-ec2.yaml": (1, {"providers.crossplaneAws.enabled": "true"}),
  "templates/providers/shared-pg.yaml": (2, {}),
  "templates/providers/profile-policies.yaml": (1, {}),
  "templates/observability/prometheus.yaml": (7, {}),
}


@pytest.mark.parametrize(("template_path", "expected"), CHART_TEMPLATE_OBJECT_COUNTS.items())
def test_chart_template_object_count_has_not_drifted(template_path, expected):
  count, set_values = expected
  args = ["helm", "template", local.CHART_NAME, str(local.repo_root() / local.CHART_DIR), "--show-only", template_path]
  for key, value in set_values.items():
    args.extend(["--set", f"{key}={value}"])
  manifest = subprocess.run(args, capture_output=True, text=True, check=True).stdout
  objects = [document for document in yaml.safe_load_all(manifest) if document is not None]
  assert len(objects) == count, [document.get("kind") for document in objects]
