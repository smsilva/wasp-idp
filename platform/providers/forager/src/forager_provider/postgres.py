"""postgres provisioners (ADR 0031). The contract of every provisioner:

- ensure(request, params, vcluster, secrets) -> (state, message, outputs, secret_ref), where state is
  Provisioning, Ready or Failed; called on every pass until Ready, so it is idempotent;
- delete(request, vcluster, secrets): undo what ensure made. vcluster is None when the environment
  is going away: what lived in it goes with it, what lives outside (compose) is still undone.

provision: a dedicated Postgres in namespace resources of the vcluster, apart from the workloads of
namespace apps. Its name is <instance>-<resource>-<hash of the ResourceRequest>: two requests never
share objects ("a" + "b-db" and "a-b" + "db" differ), and an object owned by another request is
refused, never taken over. The password is generated once and kept in the control plane (secrets),
the source of the Secret written in namespace apps, where the workload's secretKeyRef reads it. No volume: the data goes with the pod (ephemeral environments, aws/docs/known-broken.md).

compose: a role and a database of their own in a shared instance (params.instance, shared-pg), made
through the driver with every name as an identifier. The role carries the ResourceRequest as its
comment, created in the same transaction, and the database is ours only when that role owns it: a
database or role of anyone else is refused, never taken over. The pods reach the instance through the
Service the vcluster replicates from the host into namespace resources (local_vcluster, #305).

bind: something that already exists (#306). The policy item gives the values (host, port, database,
username) and secretRef, a Secret of the credentials namespace labeled bindable: only its password is
copied into namespace apps. Nothing is generated, made or dropped in a database; delete removes only
the copy. The label keeps a policy from pointing at the credentials the Forager keeps there itself
(the shared instances' admin, the passwords of other requests).
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
HOST = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?(\.[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?)*")
PORT_NUMBER = re.compile(r"[0-9]{1,5}")
SQL_NAME = re.compile(r"[a-z_][a-z0-9_-]{0,62}")


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
      if vcluster is not None and _owned(vcluster.get(api_version, kind, namespace, name), owner):
        vcluster.delete(api_version, kind, namespace, name)
    secrets.delete(request["metadata"]["name"])


def shared_instance(params: dict) -> str:
  instance = (params or {}).get("instance") or ""
  if not DNS_LABEL.fullmatch(instance):
    raise InvalidName(f"{instance!r} is not a shared instance (params.instance)")
  return instance


class Compose:
  def __init__(self, instances):
    self.instances = instances  # instance name -> its admin connection (store.SharedInstances)

  def ensure(self, request: dict, params: dict, vcluster, secrets) -> tuple[str, str, dict, dict]:
    instance, name, owner = shared_instance(params), object_name(request), request["metadata"]["name"]
    if not _owned(vcluster.get("v1", "Secret", SECRET_NAMESPACE, name), owner):
      raise InvalidName(f"Secret {SECRET_NAMESPACE}/{name} already exists and belongs to something else")
    server = self.instances.of(instance)
    if server.claimed_by(name) not in (None, owner):
      raise InvalidName(f"database or role {name} in {instance} already exists and belongs to something else")
    password = password_of(request, secrets)
    server.ensure(name, password, owner)
    labels = {"app.kubernetes.io/name": "postgres", "app.kubernetes.io/instance": name, "app.kubernetes.io/managed-by": MANAGER}
    # resources: where the vcluster replicates the shared instance's Service.
    for obj in (
      {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}},
      {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": SECRET_NAMESPACE}},
      {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": SECRET_NAMESPACE, "labels": labels, "annotations": {OWNER: owner}}, "type": "Opaque", "stringData": {"password": password}},
    ):
      vcluster.apply(obj, MANAGER)
    outputs = {"host": f"{instance}.{NAMESPACE}", "port": PORT, "name": name, "database": name, "username": name}
    return "Ready", f"database {name} ready in {instance}", outputs, {"name": name, "keys": ["password"]}

  def delete(self, request: dict, vcluster, secrets) -> None:
    name, owner = object_name(request), request["metadata"]["name"]
    try:
      instance = shared_instance(request["spec"].get("params"))
    except InvalidName:
      instance = None  # ensure never got past it: nothing was made in an instance
    if instance is not None:
      server = self.instances.of(instance)
      if server.claimed_by(name) == owner:
        server.drop(name)
    if vcluster is not None and _owned(vcluster.get("v1", "Secret", SECRET_NAMESPACE, name), owner):
      vcluster.delete("v1", "Secret", SECRET_NAMESPACE, name)
    secrets.delete(owner)


def bind_params(params: dict) -> dict:
  """The values of a bind, each checked against what it may look like."""
  params = params or {}
  checks = (("secretRef", DNS_LABEL), ("host", HOST), ("port", PORT_NUMBER), ("database", SQL_NAME), ("username", SQL_NAME))
  values = {"port": str(PORT)} | {key: str(value) for key, value in params.items()}
  for key, pattern in checks:
    if not pattern.fullmatch(values.get(key) or "") or (key == "host" and len(values[key]) > 253):
      raise InvalidName(f"bind needs a valid params.{key}, got {params.get(key)!r}")
  return values


class Bind:
  def __init__(self, sources):
    self.sources = sources  # bindable Secrets of the credentials namespace (store.BindSources)

  def ensure(self, request: dict, params: dict, vcluster, secrets) -> tuple[str, str, dict, dict]:
    values, name, owner = bind_params(params), object_name(request), request["metadata"]["name"]
    if not _owned(vcluster.get("v1", "Secret", SECRET_NAMESPACE, name), owner):
      raise InvalidName(f"Secret {SECRET_NAMESPACE}/{name} already exists and belongs to something else")
    password = self.sources.password(values["secretRef"])
    labels = {"app.kubernetes.io/name": "postgres", "app.kubernetes.io/instance": name, "app.kubernetes.io/managed-by": MANAGER}
    for obj in (
      {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": SECRET_NAMESPACE}},
      {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": SECRET_NAMESPACE, "labels": labels, "annotations": {OWNER: owner}}, "type": "Opaque", "stringData": {"password": password}},
    ):
      vcluster.apply(obj, MANAGER)
    outputs = {"host": values["host"], "port": int(values["port"]), "name": values["database"], "database": values["database"], "username": values["username"]}
    return "Ready", f"bound to {values['database']} at {values['host']}", outputs, {"name": name, "keys": ["password"]}

  def delete(self, request: dict, vcluster, secrets) -> None:
    name, owner = object_name(request), request["metadata"]["name"]
    if vcluster is not None and _owned(vcluster.get("v1", "Secret", SECRET_NAMESPACE, name), owner):
      vcluster.delete("v1", "Secret", SECRET_NAMESPACE, name)


def provisioners(instances, sources) -> dict:
  return {"postgres/provision": Provision(), "postgres/compose": Compose(instances), "postgres/bind": Bind(sources)}

