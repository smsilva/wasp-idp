from __future__ import annotations

import hashlib

import yaml
from kubernetes import client, config, dynamic, watch

GROUP = "platform.wasp.silvios.me"
CATALOG_GROUP = f"catalog.{GROUP}"
VERSION = "v1alpha1"
REVISIONS = "workloadrevisions"
INSTANCES = "workloadinstances"
REQUESTS = "resourcerequests"
ROUTES = "workloadroutes"
# The in-cluster address of the vcluster API server (ClusterIP on 443, #307), as the Platform API reaches
# it (credentials.py):
# status.kubeconfigData points to 127.0.0.1, for the host.
SERVER = "https://vcluster.env-{name}"


class Store:
  """Revisions, instances, environments and versions in the control plane cluster."""

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
      if error.status == 404:
        return None
      raise

  def list(self, plural: str) -> tuple[list[dict], str]:
    """Revisions or routes, and the resourceVersion to watch from."""
    return self._list(GROUP, plural)

  def list_instances(self) -> list[dict]:
    return self._list(GROUP, INSTANCES)[0]

  def watch(self, plural: str, resource_version: str, timeout_seconds: int):
    stream = watch.Watch().stream(
      self.api.list_namespaced_custom_object,
      GROUP, VERSION, self.namespace, plural,
      resource_version=resource_version,
      timeout_seconds=timeout_seconds,
    )
    for event in stream:
      yield event["type"], event["object"]

  def patch_route_status(self, name: str, status: dict) -> None:
    self.api.patch_namespaced_custom_object_status(GROUP, VERSION, self.namespace, ROUTES, name, {"status": status})

  def add_route_finalizer(self, route: dict, finalizer: str) -> None:
    self._finalizers(route, [*(route["metadata"].get("finalizers") or []), finalizer])

  def remove_route_finalizer(self, route: dict, finalizer: str) -> None:
    self._finalizers(route, [item for item in route["metadata"].get("finalizers") or [] if item != finalizer])

  def _finalizers(self, route: dict, finalizers: list[str]) -> None:
    """A JSON merge patch replaces the whole list; the resourceVersion makes a concurrent change a 409,
    tried again on the next pass."""
    body = {"metadata": {"finalizers": finalizers, "resourceVersion": route["metadata"]["resourceVersion"]}}
    try:
      self.api.patch_namespaced_custom_object(GROUP, VERSION, self.namespace, ROUTES, route["metadata"]["name"], body)
    except client.ApiException as error:
      if error.status != 404:
        raise
    route["metadata"]["finalizers"] = finalizers

  def get_environment(self, name: str) -> dict | None:
    return self._get(GROUP, "environments", name)

  def get_version(self, name: str) -> dict | None:
    return self._get(CATALOG_GROUP, "versions", name)

  def patch_revision_status(self, name: str, status: dict) -> None:
    self.api.patch_namespaced_custom_object_status(GROUP, VERSION, self.namespace, REVISIONS, name, {"status": status})

  def create_instance(self, body: dict) -> None:
    try:
      self.api.create_namespaced_custom_object(GROUP, VERSION, self.namespace, INSTANCES, body)
    except client.ApiException as error:
      if error.status != 409:
        raise

  def patch_instance_status(self, name: str, status: dict) -> None:
    self.api.patch_namespaced_custom_object_status(GROUP, VERSION, self.namespace, INSTANCES, name, {"status": status})

  def get_resource_request(self, name: str) -> dict | None:
    return self._get(GROUP, REQUESTS, name)

  def delete_resource_requests(self, environment: str, instance: str) -> None:
    selector = f"{GROUP}/environment={environment},{GROUP}/instance={instance}"
    for item in self.api.list_namespaced_custom_object(GROUP, VERSION, self.namespace, REQUESTS, label_selector=selector)["items"]:
      try:
        self.api.delete_namespaced_custom_object(GROUP, VERSION, self.namespace, REQUESTS, item["metadata"]["name"])
      except client.ApiException as error:
        if error.status != 404:
          raise

  def delete_instance(self, name: str) -> None:
    try:
      self.api.delete_namespaced_custom_object(GROUP, VERSION, self.namespace, INSTANCES, name)
    except client.ApiException as error:
      if error.status != 404:
        raise


class Vcluster:
  """One environment's vcluster, reached with the admin kubeconfig its provider published."""

  def __init__(self, api_client: client.ApiClient):
    self.dynamic = dynamic.DynamicClient(api_client)
    self.apps = client.AppsV1Api(api_client)
    self.api_client = api_client

  def apply(self, obj: dict, manager: str) -> None:
    resource = self.dynamic.resources.get(api_version=obj["apiVersion"], kind=obj["kind"])
    self.dynamic.server_side_apply(resource, body=obj, namespace=obj["metadata"].get("namespace"), field_manager=manager, force_conflicts=True)

  def delete(self, api_version: str, kind: str, namespace: str, name: str) -> None:
    resource = self.dynamic.resources.get(api_version=api_version, kind=kind)
    try:
      self.dynamic.delete(resource, name=name, namespace=namespace)
    except dynamic.exceptions.NotFoundError:
      pass

  def get(self, api_version: str, kind: str, namespace: str, name: str) -> dict | None:
    resource = self.dynamic.resources.get(api_version=api_version, kind=kind)
    try:
      return self.dynamic.get(resource, name=name, namespace=namespace).to_dict()
    except dynamic.exceptions.NotFoundError:
      return None

  def service_port(self, namespace: str, name: str) -> int | None:
    """The first port of a Service, or None without it."""
    try:
      service = client.CoreV1Api(self.api_client).read_namespaced_service(name, namespace)
    except client.ApiException as error:
      if error.status == 404:
        return None
      raise
    ports = service.spec.ports or []
    return ports[0].port if ports else None

  def deployment(self, namespace: str, name: str) -> dict | None:
    try:
      # camelCase, as the kube API writes it
      return self.api_client.sanitize_for_serialization(self.apps.read_namespaced_deployment(name, namespace))
    except client.ApiException as error:
      if error.status == 404:
        return None
      raise


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
