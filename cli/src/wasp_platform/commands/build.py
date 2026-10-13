"""platform build: a branch becomes a version, without waiting for a merge (#206).

The platform does not build: it dispatches the repo's platform-build workflow on GitHub Actions,
follows the run, validates app-spec.yaml (Score) and registers the version in the index.
"""
import time
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, examples, fail, print_json, print_table, success

app = typer.Typer(help="Builds: a branch of a component becomes a version in the registry.", no_args_is_help=True)

# Ready=False with these reasons does not heal by waiting: --wait stops at once.
FINAL = {
  "WorkflowNotFound", "BranchNotFound", "BuildFailed", "ContractViolation", "InvalidSpec", "VersionConflict", "GitHubRejected",
  "ConnectionNotFound", "ConnectionNotReady", "CredentialMissing", "WorkflowOutdated",
}


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def _ready(build: dict) -> dict:
  return next((item for item in build.get("conditions") or [] if item["type"] == "Ready"), {})


def _resources(build: dict) -> str:
  """db (postgres), dns, route: the name, and the type when it differs."""
  items = (build.get("appSpec") or {}).get("resources") or []
  return ", ".join(item["name"] if item["name"] == item["type"] else f"{item['name']} ({item['type']})" for item in items)


def summary(build: dict) -> list[str]:
  """The lines of the deck (#202), from what the controller recorded."""
  result = build["result"]
  resources = _resources(build)
  image = result["image"].rsplit("/", 1)[-1]
  where = f"{build['registry']} ({result['image']})" if build.get("registry") else result["image"]
  return [
    f"app-spec.yaml valid · {resources}" if resources else "app-spec.yaml valid",
    f"image {image}:{result['version']} pushed to {where}",
  ]


def _failure(build: dict) -> None:
  """Why the build stopped: the reason, the errors of app-spec.yaml, the run."""
  ready = _ready(build)
  for error in build.get("errors") or []:
    typer.secho(f"  {error['field']}: {error['reason']}", fg=typer.colors.RED, err=True)
  if build.get("runUrl") and build["runUrl"] not in (ready.get("message") or ""):
    typer.echo(f"  run: {build['runUrl']}", err=True)
  fail(f"{build['name']}: {ready['reason']}: {ready.get('message')}")


def _wait(client: PlatformClient, build: dict, timeout: int, quiet: bool) -> dict:
  deadline = time.monotonic() + timeout
  announced = False
  while True:
    if not announced and build.get("commit") and not quiet:
      typer.echo(f"building from {build['branch']} @ {build['commit'][:7]} …")
      announced = True
    ready = _ready(build)
    if ready.get("status") == "True":
      return build
    if ready.get("reason") in FINAL:
      _failure(build)
    if time.monotonic() > deadline:
      fail(f"{build['name']} not done after {timeout}s (status: {build['status']}); follow it with: platform build get {build['name']}")
    time.sleep(5)
    build = client.get_build(build["name"])


@app.command("create", epilog=examples(
  "platform build create --component hello-api --branch feat/greetings --wait",
  "platform build create --component hello-api --branch main --version 1.0.0 --registry ghcr-wasp-foundry",
))
def create(
  component: Annotated[str, typer.Option(help="Component to build, from the index.")],
  branch: Annotated[str, typer.Option(help="Branch of the component's repo.")],
  version: Annotated[str | None, typer.Option(help="Version for the CI to use; by default the CI computes it from the Conventional Commits.")] = None,
  registry: Annotated[str | None, typer.Option(help="Registry to push to (platform registry list); by default the default registry.")] = None,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until the version is registered.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait with --wait.")] = 1200,
  output: OutputOption = Format.table,
):
  """Build a branch: dispatch the repo's platform-build workflow and register the version."""
  body = {"component": component, "branch": branch, "version": version, "registry": registry}
  client = _client()
  try:
    build = client.create_build({key: value for key, value in body.items() if value is not None})
    if wait:
      build = _wait(client, build, timeout, quiet=output == Format.json)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(build)
  elif wait:
    for line in summary(build):
      success(line)
  else:
    typer.echo(f"build {build['name']}: {component} from {branch} dispatched, pushing to {build.get('registry') or '—'} …")
    typer.echo(f"follow it with: platform build get {build['name']}")


@app.command("list", epilog=examples(
  "platform build list --component hello-api",
  "platform build list --component hello-api --output json",
))
def list_(
  component: Annotated[str, typer.Option(help="Component whose versions to list.")],
  output: OutputOption = Format.table,
):
  """List the versions of a component, newest first: only builds whose app-spec.yaml is valid."""
  try:
    items = _client().list_versions(component)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(items)
    return
  print_table(
    ["NAME", "VERSION", "BRANCH", "REGISTRY", "CREATED"],
    [[item["name"], item["version"], item.get("branch") or "—", item.get("registry") or "—", item.get("createdAt") or "—"] for item in items],
  )


def _build_of(client: PlatformClient, name: str) -> dict:
  """A build by its name or by the name of its version (the NAME of build list, #408)."""
  try:
    return client.get_build(name)
  except ApiError as error:
    if error.status != 404:
      raise
    version = next((item for item in client.list_versions() if item["name"] == name), None)
    if version is None:
      raise
  if not version.get("build"):
    raise ApiError(f"version {name} was registered without a build")
  try:
    return client.get_build(version["build"])
  except ApiError as error:
    if error.status != 404:
      raise
    raise ApiError(f"version {name}: its build {version['build']} is gone (builds are kept for 24 h after they end)")


@app.command("get", epilog=examples(
  "platform build get hello-api-6cf484",
  "platform build get hello-api.0.1.0-greetings.b5f9569",
))
def get(
  name: Annotated[str, typer.Argument(help="A build (from build create) or a version (the NAME column of build list).")],
  output: OutputOption = Format.table,
):
  """Show a build and its steps (kept for 24 h after it ends)."""
  try:
    build = _build_of(_client(), name)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(build)
    return
  result = build.get("result") or {}
  typer.echo(f"build/{build['name']} ({build['status']})")
  for field, value in (
    ("component", build.get("component")),
    ("branch", build.get("branch")),
    ("version", result.get("version") or build.get("requestedVersion")),
    ("registry", f"{build['registry']} ({build.get('image')})" if build.get("registry") else None),
    ("commit", (build.get("commit") or "")[:7]),
    ("run", build.get("runUrl")),
  ):
    typer.echo(f"  {field.ljust(13)} {value or '—'}")
  for condition in build.get("conditions") or []:
    if condition["type"] == "Ready":
      continue
    mark = "✓" if condition["status"] == "True" else ("…" if condition.get("reason") in ("Queued",) else "✗")
    typer.echo(f"  {mark} {condition['type'].ljust(13)} {condition.get('message') or condition.get('reason')}")
  for error in build.get("errors") or []:
    typer.echo(f"      {error['field']}: {error['reason']}")
