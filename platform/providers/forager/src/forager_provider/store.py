from __future__ import annotations

import base64
import hashlib

import yaml
from kubernetes import client, config, dynamic, watch

from .shared import SharedPostgres

GROUP = "platform.wasp.silvios.me"
CATALOG_GROUP = f"catalog.{GROUP}"
VERSION = "v1alpha1"
REVISIONS = "workloadrevisions"
REQUESTS = "resourcerequests"
# The in-cluster address of the vcluster API server (ClusterIP on 443, #307), as the Platform API
# reaches it (credentials.py).
SERVER = "https://vcluster.env-{name}"


def _missing(error: client.ApiException) -> bool:
  return error.status == 404


class Store:
  """Revisions, resource requests, policies and the catalog in the control plane cluster."""

  def __init__(self, namespace: str, context: str | None = None):
    try:
      config.load_incluster_config()
    except config.ConfigException:
      config.load_kube_config(context=context)
    self.namespace = namespace
    self.api = client.CustomObjectsApi()

  def _list(self, group: str, plural: str) -> tuple[list[dict], str]:
    result = self.api.list_namespaced_custom_object(group, VERSION, self.namespace, plural)
    return result["items"], result["metadata"]["resourceVersion"]

  def _get(self, group: str, plural: str, name: str) -> dict | None:
    try:
      return self.api.get_namespaced_custom_object(group, VERSION, self.namespace, plural, name)
    except client.ApiException as error:
      if _missing(error):
        return None
      raise

  def list_revisions(self) -> tuple[list[dict], str]:
    return self._list(GROUP, REVISIONS)

  def watch_revisions(self, resource_version: str, timeout_seconds: int):
    stream = watch.Watch().stream(
      self.api.list_namespaced_custom_object,
      GROUP, VERSION, self.namespace, REVISIONS,
      resource_version=resource_version,
      timeout_seconds=timeout_seconds,
    )
    for event in stream:
      yield event["type"], event["object"]

  def list_requests(self) -> list[dict]:
    return self._list(GROUP, REQUESTS)[0]

  def list_policies(self) -> list[dict]:
    return self._list(GROUP, "bindingpolicies")[0]

  def get_environment(self, name: str) -> dict | None:
    return self._get(GROUP, "environments", name)

  def get_version(self, name: str) -> dict | None:
    return self._get(CATALOG_GROUP, "versions", name)

  def get_component(self, name: str) -> dict | None:
    return self._get(CATALOG_GROUP, "components", name)

  def create_catalog_resource(self, body: dict) -> None:
    try:
      self.api.create_namespaced_custom_object(CATALOG_GROUP, VERSION, self.namespace, "resources", body)
    except client.ApiException as error:
      if error.status != 409:
        raise

  def create_request(self, body: dict) -> dict:
    return self.api.create_namespaced_custom_object(GROUP, VERSION, self.namespace, REQUESTS, body)

  def patch_request(self, name: str, patch: dict) -> None:
    self.api.patch_namespaced_custom_object(GROUP, VERSION, self.namespace, REQUESTS, name, patch)

  def patch_request_status(self, name: str, status: dict) -> None:
    self.api.patch_namespaced_custom_object_status(GROUP, VERSION, self.namespace, REQUESTS, name, {"status": status})


class Secrets:
  """Generated credentials, one Secret per ResourceRequest in a namespace of their own: the provider
  never reads the Secrets of platform-system (SCM credentials)."""

  KEY = "value"

  def __init__(self, namespace: str):
    self.namespace = namespace
    self.api = client.CoreV1Api()

  def _name(self, request: str) -> str:
    return f"resource.{request}"

  def get(self, request: str) -> str | None:
    try:
      secret = self.api.read_namespaced_secret(self._name(request), self.namespace)
    except client.ApiException as error:
      if _missing(error):
        return None
      raise
    return base64.b64decode((secret.data or {})[self.KEY]).decode()

  def put(self, request: str, value: str) -> None:
    body = client.V1Secret(metadata=client.V1ObjectMeta(name=self._name(request), labels={"app.kubernetes.io/managed-by": "platform-forager"}), string_data={self.KEY: value})
    self.api.create_namespaced_secret(self.namespace, body)

  def delete(self, request: str) -> None:
    try:
      self.api.delete_namespaced_secret(self._name(request), self.namespace)
    except client.ApiException as error:
      if not _missing(error):
        raise


class Vcluster:
  """One environment's vcluster, reached with the admin kubeconfig its provider published."""

  def __init__(self, api_client: client.ApiClient):
    self.dynamic = dynamic.DynamicClient(api_client)

  def apply(self, obj: dict, manager: str) -> None:
    resource = self.dynamic.resources.get(api_version=obj["apiVersion"], kind=obj["kind"])
    self.dynamic.server_side_apply(resource, body=obj, namespace=obj["metadata"].get("namespace"), field_manager=manager, force_conflicts=True)

  def get(self, api_version: str, kind: str, namespace: str, name: str) -> dict | None:
    resource = self.dynamic.resources.get(api_version=api_version, kind=kind)
    try:
      return self.dynamic.get(resource, name=name, namespace=namespace).to_dict()
    except dynamic.exceptions.NotFoundError:
      return None

  def delete(self, api_version: str, kind: str, namespace: str, name: str) -> None:
    resource = self.dynamic.resources.get(api_version=api_version, kind=kind)
    try:
      self.dynamic.delete(resource, name=name, namespace=namespace)
    except dynamic.exceptions.NotFoundError:
      pass


class Vclusters:
  """A client per environment, kept while its kubeconfig does not change (discovery is not free)."""

  def __init__(self, server: str = SERVER):
    self.server = server
    self.cache: dict[str, tuple[str, Vcluster]] = {}

  def of(self, environment: dict) -> Vcluster:
    name = environment["metadata"]["name"]
    data = environment["status"]["kubeconfigData"]
    port = environment["status"].get("port")
    key = hashlib.sha256(f"{data}{port}".encode()).hexdigest()
    cached = self.cache.get(name)
    if cached and cached[0] == key:
      return cached[1]
    kubeconfig = yaml.safe_load(data)
    kubeconfig["clusters"][0]["cluster"]["server"] = self.server.format(name=name, port=port)
    vcluster = Vcluster(config.new_client_from_config_dict(kubeconfig))
    self.cache[name] = (key, vcluster)
    return vcluster


class SharedInstances:
  """The shared instances compose provisions into (#305): Service <name> and its admin password in
  Secret <name>-admin, both in the namespace of the generated credentials, written by `platform init`."""

  def __init__(self, namespace: str):
    self.namespace = namespace
    self.api = client.CoreV1Api()

  def of(self, instance: str) -> SharedPostgres:
    secret = self.api.read_namespaced_secret(f"{instance}-admin", self.namespace)
    return SharedPostgres(f"{instance}.{self.namespace}", base64.b64decode(secret.data["password"]).decode())
