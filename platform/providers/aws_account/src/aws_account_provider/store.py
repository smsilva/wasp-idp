from __future__ import annotations

from kubernetes import client, config, watch

GROUP = "platform.wasp.silvios.me"
VERSION = "v1alpha1"
PLURAL = "cloudaccounts"
# Read by the Platform API: the principal of every trust policy, and whether the capability is served.
BASE_IDENTITY = "aws-base-identity"


class CloudAccountStore:
  """CloudAccount CRs and the base identity ConfigMap: in-cluster config, or a kubeconfig context for development."""

  def __init__(self, namespace: str, context: str | None = None):
    try:
      config.load_incluster_config()
    except config.ConfigException:
      config.load_kube_config(context=context)
    self.namespace = namespace
    self.api = client.CustomObjectsApi()
    self.core = client.CoreV1Api()

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

  def patch_status(self, name: str, status: dict) -> None:
    self.api.patch_namespaced_custom_object_status(GROUP, VERSION, self.namespace, PLURAL, name, {"status": status})

  def publish_base_identity(self, arn: str, account: str) -> None:
    body = client.V1ConfigMap(metadata=client.V1ObjectMeta(name=BASE_IDENTITY), data={"arn": arn, "account": account})
    try:
      self.core.replace_namespaced_config_map(BASE_IDENTITY, self.namespace, body)
    except client.ApiException as error:
      if error.status != 404:
        raise
      self.core.create_namespaced_config_map(self.namespace, body)

  def clear_base_identity(self) -> None:
    try:
      self.core.delete_namespaced_config_map(BASE_IDENTITY, self.namespace)
    except client.ApiException as error:
      if error.status != 404:
        raise
