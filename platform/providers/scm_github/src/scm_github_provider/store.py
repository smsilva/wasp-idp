from __future__ import annotations

import base64

from kubernetes import client, config, watch

GROUP = "platform.wasp.silvios.me"
VERSION = "v1alpha1"
PLURAL = "scmconnections"


class ConnectionStore:
  """ScmConnection CRs in the control plane cluster: in-cluster config, or a kubeconfig context for development."""

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

  def patch_spec(self, name: str, spec: dict) -> None:
    self.api.patch_namespaced_custom_object(GROUP, VERSION, self.namespace, PLURAL, name, {"spec": spec})

  def patch_status(self, name: str, status: dict) -> None:
    self.api.patch_namespaced_custom_object_status(GROUP, VERSION, self.namespace, PLURAL, name, {"status": status})


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
