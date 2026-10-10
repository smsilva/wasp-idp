from __future__ import annotations

from kubernetes import client, config, watch

GROUP = "platform.wasp.silvios.me"
VERSION = "v1alpha1"
PLURAL = "environments"


class EnvironmentStore:
  """Environment CRs in the control plane cluster: in-cluster config, or a kubeconfig context for development."""

  def __init__(self, namespace: str, context: str | None = None):
    try:
      config.load_incluster_config()
    except config.ConfigException:
      config.load_kube_config(context=context)
    self.namespace = namespace
    self.api = client.CustomObjectsApi()

  def list(self) -> tuple[list[dict], str]:
    result = self.api.list_namespaced_custom_object(GROUP, VERSION, self.namespace, PLURAL)
    return result["items"], result["metadata"]["resourceVersion"]

  def watch(self, resource_version: str, timeout_seconds: int):
    stream = watch.Watch().stream(
      self.api.list_namespaced_custom_object,
      GROUP, VERSION, self.namespace, PLURAL,
      resource_version=resource_version,
      timeout_seconds=timeout_seconds,
    )
    for event in stream:
      yield event["type"], event["object"]

  def get(self, name: str) -> dict | None:
    try:
      return self.api.get_namespaced_custom_object(GROUP, VERSION, self.namespace, PLURAL, name)
    except client.ApiException as error:
      if error.status == 404:
        return None
      raise

  def set_finalizers(self, name: str, finalizers: list[str]) -> None:
    self.api.patch_namespaced_custom_object(
      GROUP, VERSION, self.namespace, PLURAL, name, {"metadata": {"finalizers": finalizers}}
    )

  def patch_status(self, name: str, status: dict) -> None:
    self.api.patch_namespaced_custom_object_status(
      GROUP, VERSION, self.namespace, PLURAL, name, {"status": status}
    )

  def delete_namespace(self, namespace: str) -> None:
    try:
      client.CoreV1Api().delete_namespace(namespace)
    except client.ApiException as error:
      if error.status != 404:
        raise

  def delete(self, name: str) -> None:
    try:
      self.api.delete_namespaced_custom_object(GROUP, VERSION, self.namespace, PLURAL, name)
    except client.ApiException as error:
      if error.status != 404:
        raise


class KubeconfigSecrets:
  """Reads the kubeconfig vcluster exports into Secret vc-<release> of the environment namespace."""

  def __init__(self):
    self.core = client.CoreV1Api()

  def read(self, namespace: str, name: str) -> str | None:
    import base64
    try:
      secret = self.core.read_namespaced_secret(name, namespace)
    except client.ApiException as error:
      if error.status == 404:
        return None
      raise
    data = (secret.data or {}).get("config")
    return base64.b64decode(data).decode() if data else None

  def used_ports(self, label_selector: str) -> set[int]:
    """LoadBalancer ports already taken by vcluster Services, across namespaces."""
    services = self.core.list_service_for_all_namespaces(label_selector=label_selector)
    return {port.port for svc in services.items if svc.spec.type == "LoadBalancer" for port in (svc.spec.ports or [])}
