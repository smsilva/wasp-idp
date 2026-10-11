"""postgres provisioners (ADR 0031). The contract of every provisioner:

- ensure(request, params, vcluster, secrets) -> (state, message, outputs, secret_ref), where state is
  Provisioning, Ready or Failed; called on every pass until Ready, so it is idempotent;
- delete(request, vcluster, secrets): undo what ensure made.

provision: a dedicated Postgres in namespace resources of the vcluster, apart from the workloads of
namespace apps. Its name is <instance>-<resource>-<hash of the ResourceRequest>: two requests never
share objects ("a" + "b-db" and "a-b" + "db" differ), and an object owned by another request is
refused, never taken over. The password is generated once and kept in the control plane (secrets),
the source of the Secret written in namespace apps, where the workload's secretKeyRef reads it. No volume: the data goes with the pod (ephemeral environments, aws/docs/known-broken.md).
"""
import hashlib
import re
import secrets as tokens

NAMESPACE = "resources"
# Where the workload runs: a secretKeyRef only reads Secrets of its own namespace.
SECRET_NAMESPACE = "apps"
OWNER = "platform.wasp.silvios.me/resource-request"
MANAGER = "platform-forager"
IMAGE = "postgres:17-alpine"
PORT = 5432
DATABASE = "app"
# Names that end up in manifests (and, for compose, in SQL) are checked, never trusted (ADR 0031).
DNS_LABEL = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")


class InvalidName(Exception):
  pass


def object_name(request: dict) -> str:
  spec = request["spec"]
  for value in (spec["instance"], spec["resource"]):
    if not DNS_LABEL.fullmatch(value):
      raise InvalidName(f"{value!r} is not a valid name")
  digest = hashlib.sha256(request["metadata"]["name"].encode()).hexdigest()[:8]
  return f"{spec['instance']}-{spec['resource']}"[:54].rstrip("-") + f"-{digest}"


def password_of(request: dict, secrets) -> str:
  key = request["metadata"]["name"]
  password = secrets.get(key)
  if password is None:
    password = tokens.token_hex(24)
    secrets.put(key, password)
  return password


def manifests(request: str, name: str, password: str) -> list[dict]:
  labels = {"app.kubernetes.io/name": "postgres", "app.kubernetes.io/instance": name, "app.kubernetes.io/managed-by": MANAGER}
  selector = {"app.kubernetes.io/name": "postgres", "app.kubernetes.io/instance": name}
  owner = {OWNER: request}
  return [
    {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}},
    {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": SECRET_NAMESPACE}},
    {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": SECRET_NAMESPACE, "labels": labels, "annotations": owner}, "type": "Opaque", "stringData": {"password": password}},
    {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels, "annotations": owner}, "type": "Opaque", "stringData": {"password": password}},
    {
      "apiVersion": "apps/v1",
      "kind": "StatefulSet",
      "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels, "annotations": owner},
      "spec": {
        "serviceName": name,
        "replicas": 1,
        "selector": {"matchLabels": selector},
        "template": {
          "metadata": {"labels": labels},
          "spec": {"containers": [{
            "name": "postgres",
            "image": IMAGE,
            "env": [
              {"name": "POSTGRES_USER", "value": DATABASE},
              {"name": "POSTGRES_DB", "value": DATABASE},
              {"name": "POSTGRES_PASSWORD", "valueFrom": {"secretKeyRef": {"name": name, "key": "password"}}},
            ],
            "ports": [{"name": "postgres", "containerPort": PORT}],
            "readinessProbe": {"exec": {"command": ["pg_isready", "--username", DATABASE, "--dbname", DATABASE]}, "periodSeconds": 5},
          }]},
        },
      },
    },
    {"apiVersion": "v1", "kind": "Service", "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels, "annotations": owner}, "spec": {"selector": selector, "ports": [{"name": "postgres", "port": PORT}]}},
  ]


def _owned(obj: dict | None, request: str) -> bool:
  """Absent, or written for this same ResourceRequest."""
  return obj is None or ((obj.get("metadata") or {}).get("annotations") or {}).get(OWNER) == request


class Provision:
  def ensure(self, request: dict, params: dict, vcluster, secrets) -> tuple[str, str, dict, dict]:
    name, owner = object_name(request), request["metadata"]["name"]
    objects = manifests(owner, name, password_of(request, secrets))
    for obj in objects:
      if obj["kind"] != "Namespace" and not _owned(vcluster.get(obj["apiVersion"], obj["kind"], obj["metadata"]["namespace"], name), owner):
        raise InvalidName(f"{obj['kind']} {obj['metadata']['namespace']}/{name} already exists and belongs to something else")
    for obj in objects:
      vcluster.apply(obj, MANAGER)
    outputs = {"host": f"{name}.{NAMESPACE}", "port": PORT, "name": DATABASE, "database": DATABASE, "username": DATABASE}
    secret_ref = {"name": name, "keys": ["password"]}
    statefulset = vcluster.get("apps/v1", "StatefulSet", NAMESPACE, name) or {}
    if ((statefulset.get("status") or {}).get("readyReplicas") or 0) >= 1:
      return "Ready", f"postgres {name} ready in {request['spec']['environment']}", outputs, secret_ref
    return "Provisioning", f"waiting for postgres {name}", outputs, secret_ref

  def delete(self, request: dict, vcluster, secrets) -> None:
    name, owner = object_name(request), request["metadata"]["name"]
    for api_version, kind, namespace in (("v1", "Service", NAMESPACE), ("apps/v1", "StatefulSet", NAMESPACE), ("v1", "Secret", NAMESPACE), ("v1", "Secret", SECRET_NAMESPACE)):
      if _owned(vcluster.get(api_version, kind, namespace, name), owner):
        vcluster.delete(api_version, kind, namespace, name)
    secrets.delete(request["metadata"]["name"])


PROVISIONERS = {"postgres/provision": Provision()}
