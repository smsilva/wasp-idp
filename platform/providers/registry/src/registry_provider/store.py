from kubernetes import client, config, watch

GROUP = "platform.wasp.silvios.me"
VERSION = "v1alpha1"
PLURAL = "ociregistries"


class RegistryStore:
  """OCIRegistry CRs in the control plane cluster: in-cluster config, or a kubeconfig context for development."""

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

  def patch_status(self, name: str, status: dict) -> None:
    try:
      self.api.patch_namespaced_custom_object_status(GROUP, VERSION, self.namespace, PLURAL, name, {"status": status})
    except client.ApiException as error:
      # Removed while it was being checked (registry remove): nothing left to report on.
      if error.status != 404:
        raise
