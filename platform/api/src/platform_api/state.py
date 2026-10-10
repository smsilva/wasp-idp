"""State access behind the StateWriter interface (ADR 0022).

KubeApplyWriter applies the CRDs straight to the Kubernetes API of the control plane cluster.
A GitCommitWriter (GitOps) could replace it without changing the API routes.
"""
from typing import Protocol

GROUP = "platform.wasp.silvios.me"
VERSION = "v1alpha1"
ENVIRONMENTS = "environments"


class AlreadyExists(Exception):
  pass


class NotFound(Exception):
  pass


class Conflict(Exception):
  """The object changed since it was read (optimistic concurrency)."""


class StateWriter(Protocol):
  def create(self, plural: str, body: dict) -> dict: ...

  def replace_status(self, plural: str, body: dict) -> dict: ...

  def delete(self, plural: str, name: str) -> None: ...


class StateReader(Protocol):
  def get(self, plural: str, name: str) -> dict: ...

  def list(self, plural: str) -> list[dict]: ...


class KubeApplyWriter:
  """Reads and writes platform CRDs in one namespace of the control plane cluster."""

  def __init__(self, namespace: str):
    from kubernetes import client, config

    try:
      config.load_incluster_config()
    except config.ConfigException:
      config.load_kube_config()
    self.namespace = namespace
    self.api = client.CustomObjectsApi()
    self._api_exception = client.ApiException

  def create(self, plural: str, body: dict) -> dict:
    try:
      return self.api.create_namespaced_custom_object(GROUP, VERSION, self.namespace, plural, body)
    except self._api_exception as error:
      if error.status == 409:
        raise AlreadyExists(body["metadata"]["name"]) from error
      raise

  def replace_status(self, plural: str, body: dict) -> dict:
    name = body["metadata"]["name"]
    try:
      return self.api.replace_namespaced_custom_object_status(
        GROUP, VERSION, self.namespace, plural, name, body
      )
    except self._api_exception as error:
      if error.status == 409:
        raise Conflict(name) from error
      if error.status == 404:
        raise NotFound(name) from error
      raise

  def delete(self, plural: str, name: str) -> None:
    try:
      self.api.delete_namespaced_custom_object(GROUP, VERSION, self.namespace, plural, name)
    except self._api_exception as error:
      if error.status == 404:
        raise NotFound(name) from error
      raise

  def get(self, plural: str, name: str) -> dict:
    try:
      return self.api.get_namespaced_custom_object(GROUP, VERSION, self.namespace, plural, name)
    except self._api_exception as error:
      if error.status == 404:
        raise NotFound(name) from error
      raise

  def list(self, plural: str) -> list[dict]:
    return self.api.list_namespaced_custom_object(GROUP, VERSION, self.namespace, plural)["items"]
