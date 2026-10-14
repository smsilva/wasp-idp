"""Toolsets: groups of tools an agent enables by name, so it loads only the slice it uses (ADR 0027).

Every tool is a thin call to one Platform API route through the CLI client: no logic of its own.
Authorization, validation and the journal stay in the API.
"""
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from wasp_platform.client import PlatformClient

ClientFactory = Callable[[], PlatformClient]

# A Kubernetes object name (DNS label), the broadest name the API accepts in a path.
NAME = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")


def checked(name: str) -> str:
  """A name that goes into a route path. The client resolves '..' and '/' into another route
  (catalog_get of '../../environments/demo' would read the environment, kubeconfig included),
  so anything but a plain name stops here, before the API."""
  if not NAME.fullmatch(name):
    raise ToolError(f"'{name}' is not a platform name: lowercase letters, digits and '-'")
  return name


@dataclass(frozen=True)
class ToolSpec:
  name: str
  fn: Callable[..., Any]
  # Read-only by default; a write tool is registered only with --allow-writes.
  write: bool = False
  destructive: bool = False
  idempotent: bool = True


def core(client: ClientFactory) -> list[ToolSpec]:
  def whoami() -> dict[str, Any]:
    """Who the Platform API sees the caller as: sub, email, groups and teams."""
    return client().me()

  def status(capability: str | None = None) -> dict[str, Any]:
    """Each capability of the platform and whether it works (Active, NotInstalled or a failure); one capability by name.

    platform-admins also get the providers that implement it and how to fix a failing one.
    """
    if capability is None:
      return {"items": client().list_capabilities()}
    return client().get_capability(checked(capability))

  return [ToolSpec("whoami", whoami), ToolSpec("status", status)]


def environments(client: ClientFactory) -> list[ToolSpec]:
  def environments_list(all: bool = False) -> dict[str, Any]:
    """Environments the caller owns or that are shared with their teams; all=true lists every one (platform-admins only)."""
    return {"items": client().list_environments(all)}

  def environments_get(name: str) -> dict[str, Any]:
    """One environment: profile, status (pending, ready, deleting or a failure reason), expiresAt, owner and the URL of its workloads."""
    environment = client().get_environment(checked(name))
    # The personal kubeconfig of the caller (ADR 0028) never reaches the agent.
    environment.pop("kubeconfigData", None)
    return environment

  def environments_create(name: str, profile: Literal["ephemeral", "shared"], expires: str) -> dict[str, Any]:
    """Request a new environment, which expires after the given lifetime (30m, 12h, 3d or 1w).

    The platform answers right away with status pending; call environments_get until status is ready.
    """
    # The API cannot tell an agent from the user yet (ADR 0027, phase 1): this server makes the
    # lifetime mandatory for agents until #219 moves the rule to the API.
    if not expires.strip():
      raise ToolError("an agent must set expires on a new environment, such as 2h or 1d")
    return client().create_environment(name, profile, expires)

  def environments_delete(name: str) -> dict[str, Any]:
    """Delete an ephemeral environment and everything deployed in it. Answers with status deleting.

    Only ephemeral environments: a shared one is deleted by a person, with the platform CLI.
    """
    api = client()
    # Destructive actions outside ephemeral environments wait for human approval (#220): until
    # #219 lets the API tell an agent from the user, this server holds the line.
    profile = api.get_environment(checked(name))["profile"]
    if profile != "ephemeral":
      raise ToolError(f"an agent deletes only ephemeral environments; '{name}' is {profile}")
    return api.delete_environment(name)

  return [
    ToolSpec("environments_list", environments_list),
    ToolSpec("environments_get", environments_get),
    ToolSpec("environments_create", environments_create, write=True, idempotent=False),
    ToolSpec("environments_delete", environments_delete, write=True, destructive=True),
  ]


CatalogKind = Literal["domain", "system", "resource"]


def catalog(client: ClientFactory) -> list[ToolSpec]:
  """The catalog in the vocabulary of ADR 0023, read-only in phase 1: writes wait for #219."""
  def catalog_list(kind: CatalogKind | None = None, owner: str | None = None) -> dict[str, Any]:
    """Domains, systems and resources of the catalog, each with its parent; filter by kind or owner team."""
    return {"items": client().list_catalog_entities(kind, owner)}

  def catalog_get(kind: CatalogKind, name: str) -> dict[str, Any]:
    """One domain, system or resource, with the entities that point to it (dependents, as kind/name)."""
    return client().get_catalog_entity(f"{kind}s", checked(name))

  def catalog_components_list(system: str | None = None, owner: str | None = None) -> dict[str, Any]:
    """Components in the catalog index: system, owner team, type and the repo with their catalog-info.yaml."""
    return {"items": client().list_components(system, owner)}

  def catalog_components_get(name: str) -> dict[str, Any]:
    """One component, with where it runs (runningIn) in the environments the caller can use."""
    return client().get_component(checked(name))

  def catalog_components_creation_get(name: str) -> dict[str, Any]:
    """Status of a component created from a template: repo, files and conditions. Visible to who requested it."""
    return client().component_creation(checked(name))

  def catalog_templates_list() -> dict[str, Any]:
    """Templates a component can be created from (ADR 0024): type, owner and whether it is the default."""
    return {"items": client().list_templates()}

  def catalog_templates_get(name: str) -> dict[str, Any]:
    """One template: its source (repo, path, ref) and the parameters it asks for."""
    return client().get_template(checked(name))

  return [
    ToolSpec("catalog_list", catalog_list),
    ToolSpec("catalog_get", catalog_get),
    ToolSpec("catalog_components_list", catalog_components_list),
    ToolSpec("catalog_components_get", catalog_components_get),
    ToolSpec("catalog_components_creation_get", catalog_components_creation_get),
    ToolSpec("catalog_templates_list", catalog_templates_list),
    ToolSpec("catalog_templates_get", catalog_templates_get),
  ]


def builds(client: ClientFactory) -> list[ToolSpec]:
  def builds_create(component: str, branch: str, version: str | None = None, registry: str | None = None) -> dict[str, Any]:
    """Build a branch of a component: the platform dispatches the repo's CI workflow and registers the version.

    version is computed by the CI from the Conventional Commits unless given; registry defaults to the default
    registry. The platform answers right away with status pending; call builds_get until status is ready
    (about a minute) or a failure reason, then deploy the version it registered.
    """
    body = {"component": component, "branch": branch, "version": version, "registry": registry}
    return client().create_build({key: value for key, value in body.items() if value is not None})

  def builds_get(name: str) -> dict[str, Any]:
    """One build: status (pending, ready or a failure reason), the CI run URL, the commit, the result and the errors."""
    return client().get_build(checked(name))

  def builds_list(component: str | None = None) -> dict[str, Any]:
    """Builds, newest first; filter by component."""
    return {"items": client().list_builds(component)}

  def builds_versions_list(component: str | None = None) -> dict[str, Any]:
    """Versions registered by builds, newest first, with image, branch and commit: what a deploy takes; filter by component."""
    return {"items": client().list_versions(component)}

  return [
    ToolSpec("builds_create", builds_create, write=True, idempotent=False),
    ToolSpec("builds_get", builds_get),
    ToolSpec("builds_list", builds_list),
    ToolSpec("builds_versions_list", builds_versions_list),
  ]


def workloads(client: ClientFactory) -> list[ToolSpec]:
  """What runs in an environment (ADR 0033): instances, their revisions and golden signals. An instance
  is named after its component unless it is an extra one, such as a canary."""
  def workloads_list(environment: str) -> dict[str, Any]:
    """Workload instances in an environment: component, version, replicas, status, URL and resources."""
    return {"items": client().list_workloads(checked(environment))}

  def workloads_get(environment: str, instance: str) -> dict[str, Any]:
    """One workload instance: version, replicas, status, URL, its resources (database, route) and traffic."""
    return client().get_workload(checked(environment), checked(instance))

  def workloads_history(environment: str, instance: str | None = None) -> dict[str, Any]:
    """Revisions of the instances in an environment, newest first. A revision with open=true is still rolling out;
    status Succeeded or a failure reason closes it."""
    return {"items": client().workload_history(checked(environment), checked(instance) if instance else None)}

  def workloads_signals(environment: str, instance: str, window: str = "5m") -> dict[str, Any]:
    """Golden signals of an instance from the mesh, no instrumentation in the app: latency p95, traffic, errors
    and saturation over the window (minutes or hours, as 5m or 1h, at most 6h)."""
    return client().workload_signals(checked(environment), checked(instance), window)

  def workloads_deploy(environment: str, component: str, branch: str | None = None, version: str | None = None, instance: str | None = None) -> dict[str, Any]:
    """Deploy a version of a component to an environment: a new revision of the instance. Give exactly one of
    branch (the newest version built from it) or version (from builds_versions_list); the instance defaults to the
    component name, another name runs an extra instance next to it.

    The platform answers right away with the revision, open=true; call workloads_history for the instance until
    that revision closes (open=false): status Succeeded, or a failure reason. workloads_get then shows its URL.
    """
    if (branch is None) == (version is None):
      raise ToolError("give exactly one of branch or version")
    # Always named: the API refuses (409) a component other than the one the instance already runs.
    body = {"component": component, **({"branch": branch} if branch is not None else {"version": version})}
    return client().deploy_workload(checked(environment), checked(instance or component), body)

  return [
    ToolSpec("workloads_list", workloads_list),
    ToolSpec("workloads_get", workloads_get),
    ToolSpec("workloads_history", workloads_history),
    ToolSpec("workloads_signals", workloads_signals),
    ToolSpec("workloads_deploy", workloads_deploy, write=True, idempotent=False),
  ]


TOOLSETS: dict[str, Callable[[ClientFactory], list[ToolSpec]]] = {
  "core": core,
  "environments": environments,
  "catalog": catalog,
  "builds": builds,
  "workloads": workloads,
}
