"""From a Workload Spec (Score) to the Deployment and Service of an instance (ADR 0033, phase 1).

The subset accepted: containers (image, command, args, variables, resources, httpGet probes) and
service.ports. Any other field is UnsupportedSpec; declared resources are ResourcesNotSupported until
the Forager (#263) provisions them. The labels and the Service selector carry both the component
(app.kubernetes.io/name) and the instance (app.kubernetes.io/instance): a second instance of the same
component must never join the Service of the first one.
"""
import re

NAMESPACE = "apps"
MANAGER = "platform-workload"
# A rollout that makes no progress for this long ends the revision as RolloutFailed.
PROGRESS_DEADLINE_SECONDS = 120
TOP_LEVEL = {"apiVersion", "metadata", "resources", "containers", "service"}
CONTAINER_FIELDS = {"image", "command", "args", "variables", "resources", "livenessProbe", "readinessProbe"}
HTTP_GET_FIELDS = {"path", "port", "scheme", "host", "httpHeaders"}
PORT_FIELDS = {"port", "targetPort", "protocol"}
# ${metadata.<key>} is the only placeholder that resolves without resources; $${ escapes a literal ${.
PLACEHOLDER = re.compile(r"\$(\$)?\{([^}]*)\}")


class ResourcesNotSupported(Exception):
  pass


class UnsupportedSpec(Exception):
  pass


def labels(component: str, instance: str) -> dict:
  return {"app.kubernetes.io/name": component, "app.kubernetes.io/instance": instance}


def _unknown(fields: set, allowed: set, where: str) -> None:
  extra = sorted(fields - allowed)
  if extra:
    raise UnsupportedSpec(f"{where}: {', '.join(extra)} not supported in phase 1")


def _substitute(value, metadata: dict, where: str) -> str:
  def replace(match: re.Match) -> str:
    if match.group(1):
      return "${" + match.group(2) + "}"
    path = match.group(2).split(".")
    if len(path) == 2 and path[0] == "metadata" and isinstance(metadata.get(path[1]), (str, int, float)):
      return str(metadata[path[1]])
    raise UnsupportedSpec(f"{where}: ${{{match.group(2)}}} cannot be resolved in phase 1")
  return PLACEHOLDER.sub(replace, str(value))


def _probe(probe: dict, where: str) -> dict:
  _unknown(set(probe), {"httpGet"}, where)
  http_get = probe["httpGet"]
  _unknown(set(http_get), HTTP_GET_FIELDS, f"{where}.httpGet")
  return {"httpGet": http_get}


def _container(name: str, container: dict, image: str, metadata: dict) -> dict:
  where = f"containers.{name}"
  _unknown(set(container), CONTAINER_FIELDS, where)
  result = {"name": name, "image": image if container.get("image") == "." else container["image"]}
  for field in ("command", "args"):
    if container.get(field):
      result[field] = [_substitute(item, metadata, f"{where}.{field}") for item in container[field]]
  if container.get("variables"):
    result["env"] = [{"name": key, "value": _substitute(value, metadata, f"{where}.variables.{key}")} for key, value in sorted(container["variables"].items())]
  if container.get("resources"):
    result["resources"] = container["resources"]
  for probe in ("livenessProbe", "readinessProbe"):
    if container.get(probe):
      result[probe] = _probe(container[probe], f"{where}.{probe}")
  return result


def _ports(spec: dict) -> list[dict]:
  ports = []
  for name, port in sorted(((spec.get("service") or {}).get("ports") or {}).items()):
    _unknown(set(port), PORT_FIELDS, f"service.ports.{name}")
    ports.append({"name": name, "port": port["port"], "targetPort": port.get("targetPort", port["port"]), "protocol": port.get("protocol", "TCP")})
  return ports


def render(app_spec: dict, revision: dict) -> tuple[list[dict], str | None]:
  """The objects to apply, in order, and the URL of the instance inside the vcluster."""
  if app_spec.get("resources"):
    raise ResourcesNotSupported(f"resources {', '.join(sorted(app_spec['resources']))}: the platform does not provision resources yet (#263)")
  _unknown(set(app_spec), TOP_LEVEL, "spec")
  spec = revision["spec"]
  component, instance = spec["component"], spec["instance"]
  image = f"{spec['image']}@{spec['digest']}"
  metadata = app_spec.get("metadata") or {}
  containers = [_container(name, container, image, metadata) for name, container in (app_spec.get("containers") or {}).items()]
  if not containers:
    raise UnsupportedSpec("containers: at least one container is required")
  _unknown(set(app_spec.get("service") or {}), {"ports"}, "service")
  ports = _ports(app_spec)
  selector = labels(component, instance)
  common = {**selector, "app.kubernetes.io/managed-by": MANAGER}
  annotations = {"platform.wasp.silvios.me/revision": str(spec["revision"]), "platform.wasp.silvios.me/version": spec["version"]}
  replicas = (spec.get("overrides") or {}).get("replicas", 1)
  objects = [
    {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE, "labels": {"app.kubernetes.io/managed-by": MANAGER}}},
    {
      "apiVersion": "apps/v1",
      "kind": "Deployment",
      "metadata": {"name": instance, "namespace": NAMESPACE, "labels": common, "annotations": annotations},
      "spec": {
        "replicas": replicas,
        "progressDeadlineSeconds": PROGRESS_DEADLINE_SECONDS,
        "selector": {"matchLabels": selector},
        "template": {"metadata": {"labels": common, "annotations": annotations}, "spec": {"containers": containers}},
      },
    },
  ]
  url = None
  if ports:
    objects.append({
      "apiVersion": "v1",
      "kind": "Service",
      "metadata": {"name": instance, "namespace": NAMESPACE, "labels": common},
      "spec": {"selector": selector, "ports": ports},
    })
    url = f"http://{instance}.{NAMESPACE}:{ports[0]['port']}"
  return objects, url
