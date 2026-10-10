from kubernetes import client, config, watch

GROUP = "platform.wasp.silvios.me"
VERSION = "v1alpha1"
PLURAL = "environments"


class EnvironmentStore:
  """Environment CRs in the control plane cluster, seen from the host."""

  def __init__(self, namespace: str, context: str | None):
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

  def delete(self, name: str) -> None:
    try:
      self.api.delete_namespaced_custom_object(GROUP, VERSION, self.namespace, PLURAL, name)
    except client.ApiException as error:
      if error.status != 404:
        raise
