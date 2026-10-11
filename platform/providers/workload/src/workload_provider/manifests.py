"""From a Workload Spec (Score) to the Deployment and Service of an instance (ADR 0033, phase 1).

The subset accepted: containers (image, command, args, variables, resources, httpGet probes) and
service.ports. Any other field is UnsupportedSpec. Declared resources come already provisioned by the
Forager (#263), as the outputs and the secretRef of each ResourceRequest: ${resources.<name>.<key>}
resolves against the outputs, and a secret key only as the whole value of a variable, which becomes a
secretKeyRef (never inlined in the Deployment). The labels and the Service selector carry both the component
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
# ${metadata.<key>} and ${resources.<name>.<key>}; $${ escapes a literal ${.
PLACEHOLDER = re.compile(r"\$(\$)?\{([^}]*)\}")
SECRET_PLACEHOLDER = re.compile(r"\$\{resources\.([^.}]+)\.([^.}]+)\}")


class UnsupportedSpec(Exception):
  pass


def labels(component: str, instance: str) -> dict:
  return {"app.kubernetes.io/name": component, "app.kubernetes.io/instance": instance}


def _unknown(fields: set, allowed: set, where: str) -> None:
  extra = sorted(fields - allowed)
  if extra:
    raise UnsupportedSpec(f"{where}: {', '.join(extra)} not supported in phase 1")


def _substitute(value, metadata: dict, resources: dict, where: str) -> str:
  def replace(match: re.Match) -> str:
    if match.group(1):
      return "${" + match.group(2) + "}"
    path = match.group(2).split(".")
    if len(path) == 2 and path[0] == "metadata" and isinstance(metadata.get(path[1]), (str, int, float)):
      return str(metadata[path[1]])
    if len(path) == 3 and path[0] == "resources" and path[1] in resources:
      bound = resources[path[1]]
      if path[2] in ((bound.get("secretRef") or {}).get("keys") or []):
        raise UnsupportedSpec(f"{where}: ${{{match.group(2)}}} is a secret: only accepted as the whole value of a variable")
      if isinstance((bound.get("outputs") or {}).get(path[2]), (str, int, float)):
        return str(bound["outputs"][path[2]])
    raise UnsupportedSpec(f"{where}: ${{{match.group(2)}}} cannot be resolved")
  return PLACEHOLDER.sub(replace, str(value))


def _variable(key: str, value, metadata: dict, resources: dict, where: str) -> dict:
  whole = SECRET_PLACEHOLDER.fullmatch(str(value))
  if whole and whole.group(1) in resources:
    secret_ref = resources[whole.group(1)].get("secretRef") or {}
    if whole.group(2) in (secret_ref.get("keys") or []):
      return {"name": key, "valueFrom": {"secretKeyRef": {"name": secret_ref["name"], "key": whole.group(2)}}}
  return {"name": key, "value": _substitute(value, metadata, resources, f"{where}.variables.{key}")}


def _probe(probe: dict, where: str) -> dict:
  _unknown(set(probe), {"httpGet"}, where)
  http_get = probe["httpGet"]
  _unknown(set(http_get), HTTP_GET_FIELDS, f"{where}.httpGet")
  return {"httpGet": http_get}


def _container(name: str, container: dict, image: str, metadata: dict, resources: dict) -> dict:
  where = f"containers.{name}"
  _unknown(set(container), CONTAINER_FIELDS, where)
  result = {"name": name, "image": image if container.get("image") == "." else container["image"]}
  for field in ("command", "args"):
    if container.get(field):
      result[field] = [_substitute(item, metadata, resources, f"{where}.{field}") for item in container[field]]
  if container.get("variables"):
    result["env"] = [_variable(key, value, metadata, resources, where) for key, value in sorted(container["variables"].items())]
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


def render(app_spec: dict, revision: dict, resources: dict | None = None) -> tuple[list[dict], str | None]:
  """The objects to apply, in order, and the URL of the instance inside the vcluster.

  resources: {name: {outputs, secretRef}} of each provisioned resource of the Score."""
  resources = resources or {}
  _unknown(set(app_spec), TOP_LEVEL, "spec")
  spec = revision["spec"]
  component, instance = spec["component"], spec["instance"]
  image = f"{spec['image']}@{spec['digest']}"
  metadata = app_spec.get("metadata") or {}
  containers = [_container(name, container, image, metadata, resources) for name, container in (app_spec.get("containers") or {}).items()]
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
