from __future__ import annotations

from kubernetes import client, config, watch

from .reconciler import MANAGED_BY

GROUP = "platform.wasp.silvios.me"
VERSION = "v1alpha1"
ENVIRONMENTS = "environments"
CLOUD_ACCOUNTS = "cloudaccounts"
# The Crossplane API of provider-aws v2, cluster-scoped (the same as the EKS of aws/eks/providers).
AWS_GROUP, AWS_VERSION, PROVIDER_CONFIGS = "aws.upbound.io", "v1beta1", "providerconfigs"
EC2_GROUP, EC2_VERSION, VPCS = "ec2.aws.upbound.io", "v1beta1", "vpcs"


def load(context: str | None) -> None:
  try:
    config.load_incluster_config()
  except config.ConfigException:
    config.load_kube_config(context=context)


class EnvironmentStore:
  """Environment and CloudAccount CRs of the platform namespace."""

  def __init__(self, namespace: str):
    self.namespace = namespace
    self.api = client.CustomObjectsApi()

  def list(self) -> tuple[list[dict], str]:
    result = self.api.list_namespaced_custom_object(GROUP, VERSION, self.namespace, ENVIRONMENTS)
    return result["items"], result["metadata"]["resourceVersion"]

  def accounts(self) -> list[dict]:
    return self.api.list_namespaced_custom_object(GROUP, VERSION, self.namespace, CLOUD_ACCOUNTS)["items"]

  def watch(self, resource_version: str, timeout_seconds: int):
    stream = watch.Watch().stream(
      self.api.list_namespaced_custom_object,
      GROUP, VERSION, self.namespace, ENVIRONMENTS,
      resource_version=resource_version,
      timeout_seconds=timeout_seconds,
    )
    for event in stream:
      yield event["type"], event["object"]

  def get(self, name: str) -> dict | None:
    try:
      return self.api.get_namespaced_custom_object(GROUP, VERSION, self.namespace, ENVIRONMENTS, name)
    except client.ApiException as error:
      if error.status == 404:
        return None
      raise

  def set_finalizers(self, name: str, finalizers: list[str]) -> None:
    self.api.patch_namespaced_custom_object(GROUP, VERSION, self.namespace, ENVIRONMENTS, name, {"metadata": {"finalizers": finalizers}})

  def patch_status(self, name: str, status: dict) -> None:
    self.api.patch_namespaced_custom_object_status(GROUP, VERSION, self.namespace, ENVIRONMENTS, name, {"status": status})


class CrossplaneStore:
  """The ProviderConfigs and VPCs this provider writes, labelled with app.kubernetes.io/managed-by."""

  def __init__(self):
    self.api = client.CustomObjectsApi()

  def provider_configs(self) -> list[str]:
    result = self.api.list_cluster_custom_object(AWS_GROUP, AWS_VERSION, PROVIDER_CONFIGS, label_selector=f"app.kubernetes.io/managed-by={MANAGED_BY}")
    return [item["metadata"]["name"] for item in result["items"]]

  def apply_provider_config(self, body: dict) -> None:
    name = body["metadata"]["name"]
    try:
      self.api.patch_cluster_custom_object(AWS_GROUP, AWS_VERSION, PROVIDER_CONFIGS, name, {"metadata": body["metadata"], "spec": body["spec"]})
    except client.ApiException as error:
      if error.status != 404:
        raise
      self.api.create_cluster_custom_object(AWS_GROUP, AWS_VERSION, PROVIDER_CONFIGS, body)

  def delete_provider_config(self, name: str) -> None:
    self._delete(AWS_GROUP, AWS_VERSION, PROVIDER_CONFIGS, name)

  def get_vpc(self, name: str) -> dict | None:
    try:
      return self.api.get_cluster_custom_object(EC2_GROUP, EC2_VERSION, VPCS, name)
    except client.ApiException as error:
      if error.status == 404:
        return None
      raise

  def create_vpc(self, body: dict) -> None:
    self.api.create_cluster_custom_object(EC2_GROUP, EC2_VERSION, VPCS, body)

  def delete_vpc(self, name: str) -> None:
    self._delete(EC2_GROUP, EC2_VERSION, VPCS, name)

  def _delete(self, group: str, version: str, plural: str, name: str) -> None:
    try:
      self.api.delete_cluster_custom_object(group, version, plural, name)
    except client.ApiException as error:
      if error.status != 404:
        raise
