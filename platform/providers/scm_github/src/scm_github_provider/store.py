from __future__ import annotations

import base64

from kubernetes import client, config, watch

GROUP = "platform.wasp.silvios.me"
CATALOG_GROUP = f"catalog.{GROUP}"
VERSION = "v1alpha1"
PLURAL = "scmconnections"


def load_config(context: str | None = None) -> None:
  """In-cluster config, or a kubeconfig context for development."""
  try:
    config.load_incluster_config()
  except config.ConfigException:
    config.load_kube_config(context=context)


class AlreadyExists(Exception):
  pass


class ObjectStore:
  """The CRs of one plural in the control plane cluster; load_config runs first."""

  def __init__(self, namespace: str, plural: str = PLURAL, group: str = GROUP):
    self.namespace = namespace
    self.plural = plural
    self.group = group
    self.api = client.CustomObjectsApi()

  def list(self) -> tuple[list[dict], str]:
    result = self.api.list_namespaced_custom_object(self.group, VERSION, self.namespace, self.plural)
    return result["items"], result["metadata"]["resourceVersion"]

  def watch(self, resource_version: str, timeout_seconds: int):
    stream = watch.Watch().stream(
      self.api.list_namespaced_custom_object,
      self.group, VERSION, self.namespace, self.plural,
      resource_version=resource_version,
      timeout_seconds=timeout_seconds,
    )
    for event in stream:
      yield event["type"], event["object"]

  def get(self, name: str) -> dict | None:
    try:
      return self.api.get_namespaced_custom_object(self.group, VERSION, self.namespace, self.plural, name)
    except client.ApiException as error:
      if error.status == 404:
        return None
      raise

  def patch_spec(self, name: str, spec: dict) -> None:
    self.api.patch_namespaced_custom_object(self.group, VERSION, self.namespace, self.plural, name, {"spec": spec})

  def patch_status(self, name: str, status: dict) -> None:
    self.api.patch_namespaced_custom_object_status(self.group, VERSION, self.namespace, self.plural, name, {"status": status})

  def create(self, body: dict) -> dict:
    try:
      return self.api.create_namespaced_custom_object(self.group, VERSION, self.namespace, self.plural, body)
    except client.ApiException as error:
      if error.status == 409:
        raise AlreadyExists(body["metadata"]["name"]) from error
      raise

  def replace(self, body: dict) -> dict:
    """body.metadata.resourceVersion makes a concurrent change a 409."""
    return self.api.replace_namespaced_custom_object(self.group, VERSION, self.namespace, self.plural, body["metadata"]["name"], body)


class CredentialSecrets:
  """Reads the App key the Platform API wrote through its SecretStore; only this controller has get."""

  def __init__(self, namespace: str):
    self.namespace = namespace
    self.core = client.CoreV1Api()

  def private_key(self, name: str) -> str | None:
    try:
      secret = self.core.read_namespaced_secret(name, self.namespace)
    except client.ApiException as error:
      if error.status == 404:
        return None
      raise
    data = (secret.data or {}).get("privateKey")
    return base64.b64decode(data).decode() if data else None
