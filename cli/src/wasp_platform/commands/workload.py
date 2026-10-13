"""platform workload: the Workload Spec of a version and its Workload Instances (#291, #292, ADR 0033).

The Workload Spec is the app-spec.yaml (Score) of a version, immutable, kept in the version index by
the build. spec validate runs the same gate as the build on a local file, before any build. A Workload
Instance is a Workload Spec live in an environment, as a Helm release is a chart installed: each deploy
is a new revision, and its short name is <instance>@<environment>. The instance is named after its
component by default; an extra one (--instance, #294) runs another version of the same component next
to it, with a Service of its own and no traffic from the component's until a route sends some (route,
#344: by header, by baggage or by weight). apply takes the plan of an environment, a file with every
instance it runs, and writes a revision for each one that changes, as helmfile does for releases.
"""
import time
from pathlib import Path
from typing import Annotated

import typer
import yaml

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, examples, fail, print_json, print_table, success

# The kube API keeps the spec as JSON with sorted keys: the top level goes back to the order of a Score.
SCORE_ORDER = ("apiVersion", "metadata", "resources", "containers", "service")

app = typer.Typer(help="Workloads: the Workload Spec (Score) of a version, and its instances in environments.", no_args_is_help=True)
spec_app = typer.Typer(help="The Workload Spec: the app-spec.yaml (Score) of a version.", no_args_is_help=True)
app.add_typer(spec_app, name="spec")


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def _resources(items: list[dict]) -> str:
  """db (postgres), dns, route: the name, and the type when it differs."""
  return ", ".join(item["name"] if item["name"] == item["type"] else f"{item['name']} ({item['type']})" for item in items)


@spec_app.command("validate", epilog=examples("platform workload spec validate", "platform workload spec validate --file app-spec.yaml --output json"))
def validate(
  file: Annotated[Path, typer.Option(help="The Score file to validate.")] = Path("app-spec.yaml"),
  output: OutputOption = Format.table,
):
  """Validate an app-spec.yaml with the gate of the build: schema, resource types, resources in the catalog."""
  try:
    content = file.read_text(encoding="utf-8")
  except OSError as error:
    fail(f"cannot read {file}: {error.strerror}")
  try:
    result = _client().validate_workload_spec(content)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(result)
  elif result["valid"]:
    resources = _resources(result["resources"])
    success(f"{file.name} valid · {resources}" if resources else f"{file.name} valid")
  else:
    for error in result["errors"]:
      typer.secho(f"  {error['field']}: {error['reason']}", fg=typer.colors.RED, err=True)
  if not result["valid"]:
    if output == Format.json:
      raise typer.Exit(1)
    fail(f"{file.name}: {len(result['errors'])} error(s)")


@spec_app.command("get", epilog=examples("platform workload spec get --component hello-api", "platform workload spec get --component hello-api --version 0.1.0-greetings.b5f9569"))
def get(
  component: Annotated[str, typer.Option(help="Component whose spec to show.")],
  version: Annotated[str | None, typer.Option(help="Version from the index; by default the newest.")] = None,
  branch: Annotated[str | None, typer.Option(help="The newest version built from this branch.")] = None,
  output: OutputOption = Format.table,
):
  """Show the Workload Spec of a version, as YAML ready for a file."""
  if version is not None and branch is not None:
    fail("--version and --branch are exclusive")
  try:
    spec = _client().get_workload_spec(component, version, branch)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(spec)
    return
  # A YAML comment: the output stays a valid app-spec.yaml.
  typer.echo(f"# {spec['component']} {spec['version']} · {spec['branch']} @ {(spec.get('commit') or '')[:7]}")
  document = spec["appSpec"]
  ordered = {key: document[key] for key in SCORE_ORDER if key in document} | document
  typer.echo(yaml.safe_dump(ordered, sort_keys=False).rstrip())


def _replicas(item: dict) -> str:
  replicas = item.get("replicas") or {}
  return f"{replicas.get('ready')}/{replicas.get('desired')}" if replicas else "—"


InstanceOption = Annotated[str | None, typer.Option(help="Instance of the workload; needed when its component has more than one in the environment.")]


def _instance(client: PlatformClient, environment: str, component: str | None, instance: str | None) -> str:
  """The instance a command acts on: --instance, or the default instance of --component (named after it)."""
  if (component is None) == (instance is None):
    fail("give either --component or --instance")
  if instance is not None:
    return instance
  found = sorted(item["instance"] for item in client.list_workloads(environment) if item.get("component") == component)
  # --component never lands on an extra instance unasked: that would remove someone's sandbox.
  if found and found != [component]:
    fail(f"{component} has {len(found)} instance{'s' if len(found) > 1 else ''} in {environment}: {', '.join(found)}; give --instance")
  # None at all: the default instance, and the API says whether it exists.
  return component


def _wait(client: PlatformClient, revision: dict, timeout: int) -> dict:
  """Until the provider closes the revision: Succeeded, or a reason that waiting does not heal."""
  deadline = time.monotonic() + timeout
  while revision["open"]:
    if time.monotonic() > deadline:
      fail(f"{revision['instance']}@{revision['environment']} revision {revision['revision']} not done after {timeout}s ({revision['status']}: {revision.get('message') or '—'})")
    time.sleep(3)
    history = client.workload_history(revision["environment"], revision["instance"])
    revision = next(item for item in history if item["revision"] == revision["revision"])
  return revision


@app.command("deploy", epilog=examples("platform workload deploy --component hello-api --environment demo --version 0.1.0-greetings.b5f9569 --wait", "platform workload deploy --component hello-api --environment demo --instance hello-api-canary --branch feat/greetings --replicas 2"))
def deploy(
  component: Annotated[str, typer.Option(help="Component to deploy.")],
  environment: Annotated[str, typer.Option(help="Environment to deploy to.")],
  instance: Annotated[str | None, typer.Option(help="Instance to deploy; by default the component name. Another name runs an extra instance next to it.")] = None,
  version: Annotated[str | None, typer.Option(help="Version from the index.")] = None,
  branch: Annotated[str | None, typer.Option(help="The newest version built from this branch, pinned in the revision.")] = None,
  replicas: Annotated[int | None, typer.Option(min=0, max=20, help="Replicas in this environment; by default 1.")] = None,
  resource_class: Annotated[list[str] | None, typer.Option("--resource-class", help="<resource>=<class>: the item of the environment policy a resource of the spec resolves with (repeatable).")] = None,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until the rollout ends.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait with --wait.")] = 300,
  output: OutputOption = Format.table,
):
  """Deploy a version to an environment: a new revision of the instance."""
  if (version is None) == (branch is None):
    fail("give either --version or --branch")
  # Always named: the API refuses (409) a component other than the one the instance already runs.
  body = {"component": component, **{key: value for key, value in (("version", version), ("branch", branch), ("replicas", replicas)) if value is not None}}
  if resource_class:
    body["resourceClasses"] = _resource_classes(resource_class)
  client = _client()
  try:
    revision = client.deploy_workload(environment, instance or component, body)
    if wait:
      revision = _wait(client, revision, timeout)
  except ApiError as error:
    fail(str(error))
  _report(client, revision, wait, output, f"deploying {revision['version']} …")


def _resource_classes(values: list[str]) -> dict[str, str]:
  classes = {}
  for value in values:
    name, _, klass = value.partition("=")
    if not name or not klass or "=" in klass:
      fail(f"--resource-class takes <resource>=<class>, got '{value}'")
    classes[name] = klass
  return classes


def _flag(item: dict) -> str:
  """--component for the default instance, --instance for an extra one."""
  if item["instance"] == item["component"]:
    return f"--component {item['component']}"
  return f"--instance {item['instance']}"


def _report(client: PlatformClient, revision: dict, wait: bool, output: Format, started: str) -> None:
  """The revision a command wrote: started, or with --wait how it ended."""
  name = f"{revision['instance']}@{revision['environment']}"
  if output == Format.json:
    print_json(revision)
    if wait and revision["status"] != "Succeeded":
      raise typer.Exit(1)
    return
  heading = f"{name} revision {revision['revision']}"
  if not wait:
    typer.echo(f"{heading}: {started}")
    # After a remove there is no workload to get: its history stays.
    follow = "history" if revision["action"] == "remove" else "get"
    typer.echo(f"follow it with: platform workload {follow} {_flag(revision)} --environment {revision['environment']}")
  elif revision["status"] != "Succeeded":
    fail(f"{heading}: {revision['status']}: {revision.get('message') or '—'}")
  elif revision["action"] == "remove":
    success(f"{heading}: removed from {revision['environment']}")
  else:
    success(f"{heading}: {revision['version']} running · {revision.get('message') or '—'}")
    _running(client, revision)


def _details(item: dict) -> list[tuple[str, str]]:
  """The url and the resources of an instance, as `get` shows them."""
  classes = (item.get("latestRevision") or {}).get("resourceClasses") or {}
  lines = [("url", item.get("publicUrl") or item.get("url") or "—")]
  for resource in item.get("resources") or []:
    klass = f", class {classes[resource['name']]}" if resource["name"] in classes else ""
    lines.append(("resource", f"{resource['name']} ({resource.get('type')}, {resource.get('mode') or '—'}{klass}): {resource.get('status') or '—'}"))
  return lines


def _running(client: PlatformClient, revision: dict) -> None:
  """Under the ✓ of a revision that ended running: where it answers and how each resource resolved (#328)."""
  try:
    item = client.get_workload(revision["environment"], revision["instance"])
  except ApiError as error:
    # The rollout succeeded: failing to show it is no reason to exit non-zero.
    typer.secho(f"⚠ cannot show the url and resources: {error}", fg=typer.colors.YELLOW, err=True)
    return
  for field, value in _details(item):
    if value != "—":
      typer.echo(f"  {field.ljust(13)} {value}")


def _previous(client: PlatformClient, environment: str, instance: str) -> int:
  """The newest revision that succeeded before the one running: what `rollback` goes back to by default."""
  running = client.get_workload(environment, instance).get("revision")
  candidates = [
    item["revision"] for item in client.workload_history(environment, instance)
    if item["action"] != "remove" and item["status"] == "Succeeded" and running is not None and item["revision"] < running
  ]
  if not candidates:
    fail(f"{instance}@{environment}: no earlier revision that succeeded to roll back to")
  return max(candidates)


@app.command("rollback", epilog=examples("platform workload rollback --component hello-api --environment demo", "platform workload rollback --instance hello-api-canary --environment demo --revision 3 --wait"))
def rollback(
  environment: Annotated[str, typer.Option(help="Environment of the workload.")],
  component: Annotated[str | None, typer.Option(help="Component of the workload.")] = None,
  instance: InstanceOption = None,
  revision: Annotated[int | None, typer.Option(min=1, help="Revision to go back to; by default the one that succeeded before the running one.")] = None,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until the rollout ends.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait with --wait.")] = 300,
  output: OutputOption = Format.table,
):
  """Roll back: a new revision with the version and overrides of an earlier one."""
  client = _client()
  try:
    name = _instance(client, environment, component, instance)
    target = revision or _previous(client, environment, name)
    created = client.deploy_workload(environment, name, {"rollbackTo": target})
    if wait:
      created = _wait(client, created, timeout)
  except ApiError as error:
    fail(str(error))
  _report(client, created, wait, output, f"rolling back to revision {target} ({created['version']}) …")


@app.command("remove", epilog=examples("platform workload remove --instance hello-api-canary --environment demo", "platform workload remove --component hello-api --environment demo --wait"))
def remove(
  environment: Annotated[str, typer.Option(help="Environment of the workload.")],
  component: Annotated[str | None, typer.Option(help="Component of the workload.")] = None,
  instance: InstanceOption = None,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until it is gone from the environment.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait with --wait.")] = 300,
  output: OutputOption = Format.table,
):
  """Remove a workload from an environment: a remove revision; the history stays with the environment."""
  client = _client()
  try:
    created = client.remove_workload(environment, _instance(client, environment, component, instance))
    if wait:
      created = _wait(client, created, timeout)
  except ApiError as error:
    fail(str(error))
  _report(client, created, wait, output, "removing …")


PLAN_KEYS = {"environment", "workloads"}


def _plan(file: Path) -> tuple[str, dict]:
  """environment and workloads of a plan file: {instance: {component?, version | branch, replicas?, resourceClasses?}}."""
  try:
    document = yaml.safe_load(file.read_text(encoding="utf-8"))
  except OSError as error:
    fail(f"cannot read {file}: {error.strerror}")
  except yaml.YAMLError as error:
    fail(f"{file}: not YAML: {error}")
  if not isinstance(document, dict):
    fail(f"{file}: a plan is a mapping with environment and workloads")
  unknown = sorted(set(document) - PLAN_KEYS)
  if unknown:
    fail(f"{file}: unknown key(s) {', '.join(unknown)}; a plan has environment and workloads")
  environment = document.get("environment")
  if not isinstance(environment, str) or not environment:
    fail(f"{file}: environment is required")
  workloads = document.get("workloads")
  # An empty plan is written as workloads: {}, so that it is never a forgotten key.
  if not isinstance(workloads, dict) or not all(isinstance(entry, dict) for entry in workloads.values()):
    fail(f"{file}: workloads is a mapping of instance to {{version | branch, replicas, resourceClasses}}; an empty plan is workloads: {{}}")
  return environment, workloads


def _target(state: dict | None) -> str:
  if not state:
    return "—"
  classes = "".join(f" {name}={klass}" for name, klass in sorted((state.get("resourceClasses") or {}).items()))
  return f"{state['version']} ×{state['replicas']}{classes}"


@app.command("apply", epilog=examples("platform workload apply --file demo-plan.yaml --dry-run", "platform workload apply --file demo-plan.yaml --prune --wait"))
def apply(
  file: Annotated[Path, typer.Option(help="The plan: environment, and workloads by instance with version or branch, replicas and resourceClasses.")],
  dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would change and exit.")] = False,
  prune: Annotated[bool, typer.Option("--prune", help="Remove the workloads of the environment that the plan leaves out.")] = False,
  wait: Annotated[bool, typer.Option("--wait", help="Wait until every rollout ends.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait for each revision with --wait.")] = 300,
  output: OutputOption = Format.table,
):
  """Apply the plan of an environment: a revision for each workload that changes."""
  environment, workloads = _plan(file)
  client = _client()
  try:
    plan = client.apply_workloads(environment, workloads, dry_run, prune)
    written = [item for item in plan["items"] if item.get("revision") is not None]
    ended = []
    if wait and not dry_run:
      for item in written:
        revision = next(entry for entry in client.workload_history(environment, item["instance"]) if entry["revision"] == item["revision"])
        ended.append(_wait(client, revision, timeout))
  except ApiError as error:
    fail(str(error))
  failed = [revision for revision in ended if revision["status"] != "Succeeded"]
  if output == Format.json:
    print_json({**plan, "revisions": ended} if ended else plan)
    if failed:
      raise typer.Exit(1)
    return
  print_table(
    ["WORKLOAD", "ACTION", "FROM", "TO", "REVISION"],
    [[f"{item['instance']}@{environment}", item["action"], _target(item["from"]), _target(item["to"]), str(item.get("revision") or "—")] for item in plan["items"]],
  )
  summary = plan["summary"]
  typer.echo(f"{environment}: {summary['add']} to add, {summary['change']} to change, {summary['remove']} to remove")
  if dry_run:
    typer.echo("dry run: nothing applied")
  elif written and not wait:
    typer.echo(f"follow it with: platform workload list --environment {environment}")
  for revision in ended:
    heading = f"{revision['instance']}@{environment} revision {revision['revision']}"
    if revision["status"] != "Succeeded":
      typer.secho(f"✗ {heading}: {revision['status']}: {revision.get('message') or '—'}", fg=typer.colors.RED, err=True)
    elif revision["action"] == "remove":
      success(f"{heading}: removed from {environment}")
    else:
      success(f"{heading}: {revision['version']} running · {revision.get('message') or '—'}")
      _running(client, revision)
  if failed:
    fail(f"{environment}: {len(failed)} of {len(ended)} revision(s) did not succeed")


@app.command("list", epilog=examples("platform workload list --environment demo", "platform workload list --environment demo --output json"))
def list_(
  environment: Annotated[str, typer.Option(help="Environment whose workloads to list.")],
  output: OutputOption = Format.table,
):
  """List the workloads of an environment: version, status, replicas, revision, URL (the public one when it has a route)."""
  try:
    items = _client().list_workloads(environment)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(items)
    return
  print_table(
    ["WORKLOAD", "COMPONENT", "VERSION", "STATUS", "REPLICAS", "REVISION", "TRAFFIC", "URL"],
    [[item["name"], item.get("component") or "—", item.get("version") or "—", item["status"], _replicas(item), str(item.get("revision") or "—"), item.get("traffic") or "—", item.get("publicUrl") or item.get("url") or "—"] for item in items],
  )


@app.command("get", epilog=examples("platform workload get --component hello-api --environment demo", "platform workload get --instance hello-api-canary --environment demo"))
def get_(
  environment: Annotated[str, typer.Option(help="Environment of the workload.")],
  component: Annotated[str | None, typer.Option(help="Component of the workload.")] = None,
  instance: InstanceOption = None,
  output: OutputOption = Format.table,
):
  """Show a workload in an environment and its newest revision."""
  client = _client()
  try:
    item = client.get_workload(environment, _instance(client, environment, component, instance))
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(item)
    return
  latest = item["latestRevision"]
  typer.echo(f"{item['name']} ({item['status']})")
  for field, value in (
    ("component", item.get("component")),
    ("version", item.get("version")),
    ("image", item.get("image")),
    ("replicas", _replicas(item)),
    ("revision", item.get("revision")),
    ("traffic", item.get("traffic")),
    _details(item)[0],
    *((("internal url", item.get("url")),) if item.get("publicUrl") else ()),
    ("message", item.get("message")),
  ):
    typer.echo(f"  {field.ljust(13)} {value or '—'}")
  for field, value in _details(item)[1:]:
    typer.echo(f"  {field.ljust(13)} {value}")
  if latest["revision"] != item.get("revision"):
    what = " ".join(part for part in (latest["action"], latest.get("version")) if part)
    typer.echo(f"  {'newest'.ljust(13)} revision {latest['revision']} ({what}): {latest['status']}: {latest.get('message') or '—'}")


@app.command("history", epilog=examples("platform workload history --environment demo", "platform workload history --environment demo --component hello-api"))
def history(
  environment: Annotated[str, typer.Option(help="Environment whose revisions to list.")],
  component: Annotated[str | None, typer.Option(help="Only the revisions of this component, in all its instances.")] = None,
  instance: Annotated[str | None, typer.Option(help="Only the revisions of this instance.")] = None,
  output: OutputOption = Format.table,
):
  """List the revisions of an environment, oldest first: who asked for what, and how it ended."""
  try:
    items = _client().workload_history(environment, instance, component)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(items)
    return
  print_table(
    ["WORKLOAD", "REVISION", "ACTION", "VERSION", "STATUS", "BY", "CREATED"],
    [[f"{item['instance']}@{item['environment']}", str(item["revision"]), item["action"], item.get("version") or "—", item["status"], item.get("requestedBy") or "—", item.get("createdAt") or "—"] for item in items],
  )


def _pair(value: str, option: str) -> tuple[str, str]:
  key, sep, val = value.partition("=")
  if not sep or not key or not val:
    fail(f"{option} takes key=value, e.g. {option} x-sandbox=pr-42")
  return key, val


def _match_key(rule: dict) -> tuple | None:
  """What a rule matches on; header names are case-insensitive. None for the weights rule."""
  match = rule.get("match") or {}
  if match.get("header"):
    return ("header", match["header"]["name"].lower(), match["header"]["value"])
  if match.get("baggage"):
    return ("baggage", match["baggage"]["key"], match["baggage"]["value"])
  return None


def routed_rules(rules: list[dict], component: str, to: str, header: tuple[str, str] | None = None, baggage: tuple[str, str] | None = None, weight: int | None = None) -> list[dict]:
  """The rules after one change: a match rule replaces the one with the same match (header names are
  case-insensitive); a weight sets the share of one instance in the weights rule (the last), and the
  main instance takes the rest. Weight 0 takes the instance out, and a weights rule left with the main
  instance alone goes away."""
  if weight is None:
    match = {"header": {"name": header[0], "value": header[1]}} if header else {"baggage": {"key": baggage[0], "value": baggage[1]}}
    new = {"match": match, "to": to}
    kept = [rule for rule in rules if "weights" not in rule and _match_key(rule) != _match_key(new)]
    # The weights rule stays the last one.
    return [*kept, new, *(rule for rule in rules if "weights" in rule)]
  if to == component:
    fail(f"--weight sets the share of another instance of {component}: {component} takes the rest")
  current = next((dict(rule["weights"]) for rule in rules if "weights" in rule), {})
  current.pop(component, None)
  if weight:
    current[to] = weight
  else:
    current.pop(to, None)
  others = sum(current.values())
  if others > 100:
    fail(f"the weights of the other instances add up to {others}%, more than 100%")
  kept = [rule for rule in rules if "weights" not in rule]
  if not current:
    return kept
  weights = dict(sorted(current.items()))
  if others < 100:
    weights[component] = 100 - others
  return [*kept, {"weights": weights}]


def _rule_text(rule: dict) -> str:
  match = rule.get("match") or {}
  if match.get("header"):
    return f"{match['header']['name']}={match['header']['value']} → {rule['to']}"
  if match.get("baggage"):
    return f"baggage {match['baggage']['key']}={match['baggage']['value']} → {rule['to']}"
  return " · ".join(f"{instance} {weight}%" for instance, weight in rule["weights"].items())


@app.command("route", epilog=examples("platform workload route --component hello-api --environment demo --to hello-api-canary --header x-sandbox=pr-42", "platform workload route --component hello-api --environment demo --to hello-api-canary --weight 10"))
def route(
  component: Annotated[str, typer.Option(help="Component whose traffic to route; the route attaches to the Service of its main instance.")],
  environment: Annotated[str, typer.Option(help="Environment of the instances.")],
  to: Annotated[str | None, typer.Option(help="Instance of the component that takes the matching traffic.")] = None,
  header: Annotated[str | None, typer.Option(help="name=value: requests with this header go to --to.")] = None,
  baggage: Annotated[str | None, typer.Option(help="key=value: requests with this OpenTelemetry Baggage entry go to --to.")] = None,
  weight: Annotated[int | None, typer.Option(min=0, max=100, help="Percent of the remaining traffic for --to; the main instance takes the rest, 0 takes --to out.")] = None,
  clear: Annotated[bool, typer.Option("--clear", help="Remove the route: every request goes to the main instance.")] = False,
  output: OutputOption = Format.table,
):
  """Route the traffic to a component among its instances: by header, by baggage, or by weight."""
  client = _client()
  if clear:
    if any(value is not None for value in (to, header, baggage, weight)):
      fail("--clear takes no --to, --header, --baggage nor --weight")
    try:
      result = client.delete_workload_route(environment, component)
    except ApiError as error:
      fail(str(error))
    if output == Format.json:
      print_json(result)
    else:
      success(f"route of {component} in {environment} cleared: every request goes to {component}")
    return
  if sum(value is not None for value in (header, baggage, weight)) != 1 or to is None:
    fail("give --to and one of --header, --baggage or --weight (or --clear)")
  try:
    current = client.get_workload_route(environment, component)
    # Last write wins: a change made by someone else between this read and the write below is lost.
    rules = routed_rules(
      (current or {}).get("rules") or [], component, to,
      header=_pair(header, "--header") if header else None,
      baggage=_pair(baggage, "--baggage") if baggage else None,
      weight=weight,
    )
    result = client.put_workload_route(environment, component, rules) if rules else client.delete_workload_route(environment, component)
  except ApiError as error:
    fail(str(error))
  if output == Format.json:
    print_json(result)
    return
  if not rules:
    success(f"route of {component} in {environment} cleared: every request goes to {component}")
    return
  success(f"route of {component} in {environment}:")
  for rule in rules:
    typer.echo(f"  {_rule_text(rule)}")
  if "weights" not in rules[-1]:
    typer.echo(f"  otherwise → {component}")
