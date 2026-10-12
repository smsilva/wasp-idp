from datetime import datetime, timezone

import httpx
import pytest

from registry_provider.reconciler import Reconciler

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


class FakeStore:
  def __init__(self):
    self.patches = []

  def patch_status(self, name, status):
    self.patches.append((name, status))


def registry(status=None):
  obj = {"metadata": {"name": "ghcr-wasp-foundry"}, "spec": {"vendor": "ghcr", "host": "ghcr.io", "namespace": "wasp-foundry"}}
  if status:
    obj["status"] = status
  return obj


def reconcile(handler, obj=None):
  store = FakeStore()
  http = httpx.Client(transport=httpx.MockTransport(handler))
  Reconciler(store, http, now=lambda: NOW).reconcile(obj or registry())
  return store.patches


@pytest.mark.parametrize("response,reason,message", [
  (httpx.Response(200), "Verified", "https://ghcr.io/v2/ answered 200"),
  (httpx.Response(401, headers={"www-authenticate": 'Bearer realm="https://ghcr.io/token"'}), "Verified", "https://ghcr.io/v2/ answered 401 with a token challenge"),
  (httpx.Response(401), "Unreachable", "https://ghcr.io/v2/ answered 401: not an OCI registry"),
  (httpx.Response(404), "Unreachable", "https://ghcr.io/v2/ answered 404: not an OCI registry"),
])
def test_the_distribution_api_answers(response, reason, message):
  def handler(request):
    assert str(request.url) == "https://ghcr.io/v2/"
    return response
  [(name, status)] = reconcile(handler)
  condition = status["conditions"][0]
  assert name == "ghcr-wasp-foundry"
  assert (condition["type"], condition["reason"], condition["message"], condition["lastTransitionTime"]) == ("Ready", reason, message, "2026-10-12T12:00:00Z")
  assert condition["status"] == ("True" if reason == "Verified" else "False")


def test_no_answer_is_unreachable():
  def handler(request):
    raise httpx.ConnectError("Name or service not known")
  condition = reconcile(handler)[0][1]["conditions"][0]
  assert (condition["status"], condition["reason"]) == ("False", "Unreachable")
  assert condition["message"] == "https://ghcr.io/v2/: ConnectError: Name or service not known"


def test_nothing_written_when_nothing_changed():
  current = {"conditions": [{"type": "Ready", "status": "True", "reason": "Verified", "message": "https://ghcr.io/v2/ answered 200", "lastTransitionTime": "2026-10-01T00:00:00Z"}]}
  assert reconcile(lambda request: httpx.Response(200), registry(current)) == []


def test_a_new_message_keeps_the_transition_time():
  current = {"conditions": [{"type": "Ready", "status": "True", "reason": "Verified", "message": "https://ghcr.io/v2/ answered 200", "lastTransitionTime": "2026-10-01T00:00:00Z"}]}
  headers = {"www-authenticate": "Bearer"}
  condition = reconcile(lambda request: httpx.Response(401, headers=headers), registry(current))[0][1]["conditions"][0]
  assert condition["lastTransitionTime"] == "2026-10-01T00:00:00Z"


def test_a_deleted_registry_is_left_alone():
  obj = registry()
  obj["metadata"]["deletionTimestamp"] = "2026-10-12T11:00:00Z"
  assert reconcile(lambda request: httpx.Response(200), obj) == []


def test_a_registry_removed_meanwhile_is_not_an_error(monkeypatch):
  from kubernetes import client

  from registry_provider.store import RegistryStore

  class Gone:
    def patch_namespaced_custom_object_status(self, *args):
      raise client.ApiException(status=404, reason="Not Found")

  store = RegistryStore.__new__(RegistryStore)
  store.namespace, store.api = "platform-system", Gone()
  store.patch_status("smoke-reg-from-connection", {"conditions": []})


def test_other_api_errors_still_raise():
  from kubernetes import client

  from registry_provider.store import RegistryStore

  class Broken:
    def patch_namespaced_custom_object_status(self, *args):
      raise client.ApiException(status=500, reason="Internal Server Error")

  store = RegistryStore.__new__(RegistryStore)
  store.namespace, store.api = "platform-system", Broken()
  with pytest.raises(client.ApiException):
    store.patch_status("x", {"conditions": []})
