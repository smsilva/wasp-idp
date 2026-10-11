"""SecretStore (ADR 0025): where the platform keeps credentials it receives, write-only for the API.

The API puts and deletes; it never reads a secret back, so no route can leak one. Whoever uses the
credential (the scm_github controller) reads it with its own ServiceAccount. On the local target the
store is a Kubernetes Secret in platform-system; in the cloud, the native vault behind External Secrets.
"""
from typing import Protocol

from .state import GROUP

SECRET_OF_LABEL = f"{GROUP}/secret-of"


class SecretStore(Protocol):
  def put(self, name: str, data: dict[str, str], owner: str) -> None: ...

  def delete(self, name: str) -> None: ...


class KubeSecretStore:
  """One Opaque Secret per credential, labeled with the object it belongs to (`<kind>/<name>`)."""

  def __init__(self, namespace: str):
    from kubernetes import client, config

    try:
      config.load_incluster_config()
    except config.ConfigException:
      config.load_kube_config()
    self.namespace = namespace
    self.core = client.CoreV1Api()
    self._api_exception = client.ApiException
    self._client = client

  def put(self, name: str, data: dict[str, str], owner: str) -> None:
    # A label value cannot hold "/": the kind and name are joined with "." instead.
    body = self._client.V1Secret(
      metadata=self._client.V1ObjectMeta(name=name, labels={SECRET_OF_LABEL: owner.replace("/", ".")}),
      type="Opaque",
      string_data=data,
    )
    try:
      self.core.create_namespaced_secret(self.namespace, body)
    except self._api_exception as error:
      if error.status != 409:
        raise
      # Replace without reading first: the API has no get on secrets.
      self.core.replace_namespaced_secret(name, self.namespace, body)

  def delete(self, name: str) -> None:
    try:
      self.core.delete_namespaced_secret(name, self.namespace)
    except self._api_exception as error:
      if error.status != 404:
        raise
