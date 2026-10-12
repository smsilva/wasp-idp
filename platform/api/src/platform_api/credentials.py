"""Personal credentials for environments (ADR 0028).

Each person who passes can_use gets their own ServiceAccount in the vcluster (namespace
platform-identities, named after the token `sub`) and a short-lived token for it. The kubeconfig the
API hands out carries no static credential: kubectl runs `platform environment credential <name>`,
which asks this module for a fresh token. Deleting the ServiceAccount revokes its tokens.

The API reaches each vcluster from inside the control plane cluster, with the admin kubeconfig the
provider publishes in status.kubeconfigData.
"""
import base64
import hashlib
import logging
import os
import re
import ssl
import tempfile

import httpx
import yaml

from .state import GROUP

NAMESPACE = "platform-identities"
# The minimum Kubernetes accepts for a TokenRequest: it bounds how long a revoked person keeps access.
TOKEN_SECONDS = 600
CLUSTER_ROLE = "cluster-admin"
EMAIL_ANNOTATION = f"{GROUP}/email"
MANAGED_BY = {"app.kubernetes.io/managed-by": "platform-api"}
# The in-cluster address of the vcluster API server (the chart's Service, ClusterIP on 443, #307); its
# certificate carries vcluster.env-<name>.
SERVER = "https://vcluster.env-{name}"
EXEC_API_VERSION = "client.authentication.k8s.io/v1"
DNS_LABEL = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")

log = logging.getLogger("platform-api")


class NotReady(Exception):
  pass


class VclusterUnavailable(Exception):
  pass


def identity_name(sub: str) -> str:
  """The ServiceAccount of a person: the Keycloak `sub` (a UUID) when it is a valid name, a digest otherwise."""
  if DNS_LABEL.fullmatch(sub):
    return sub
  return "sub-" + hashlib.sha256(sub.encode()).hexdigest()[:40]


def binding_name(identity: str) -> str:
  return f"platform-identity-{identity}"[:253]


def _admin_kubeconfig(obj: dict) -> dict:
  data = (obj.get("status") or {}).get("kubeconfigData")
  if not data:
    raise NotReady(obj["metadata"]["name"])
  return yaml.safe_load(data)


def personal_kubeconfig(obj: dict) -> str | None:
  """The admin kubeconfig's cluster with a user that runs the CLI for a token; None until the vcluster is ready."""
  try:
    admin = _admin_kubeconfig(obj)
  except NotReady:
    return None
  name = obj["metadata"]["name"]
  return yaml.safe_dump({
    "apiVersion": "v1",
    "kind": "Config",
    "clusters": [{"name": name, "cluster": admin["clusters"][0]["cluster"]}],
    "users": [{"name": name, "user": {"exec": {
      "apiVersion": EXEC_API_VERSION,
      "command": "platform",
      "args": ["environment", "credential", name],
      "interactiveMode": "Never",
    }}}],
    "contexts": [{"name": name, "context": {"cluster": name, "user": name}}],
    "current-context": name,
  }, sort_keys=False)


class VclusterCredentials:
  def __init__(self, server: str = SERVER, transport=None):
    self.server = server
    self.transport = transport

  def _client(self, obj: dict) -> httpx.Client:
    admin = _admin_kubeconfig(obj)
    base_url = self.server.format(name=obj["metadata"]["name"], port=(obj.get("status") or {}).get("port"))
    if self.transport:
      return httpx.Client(base_url=base_url, transport=self.transport)
    cluster = admin["clusters"][0]["cluster"]
    user = admin["users"][0]["user"]
    context = ssl.create_default_context(cadata=base64.b64decode(cluster["certificate-authority-data"]).decode())
    # load_cert_chain reads files only: the key lives on disk just for the call.
    with tempfile.TemporaryDirectory() as directory:
      cert, key = os.path.join(directory, "cert"), os.path.join(directory, "key")
      for path, field in ((cert, "client-certificate-data"), (key, "client-key-data")):
        with open(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600), "wb") as file:
          file.write(base64.b64decode(user[field]))
      context.load_cert_chain(cert, key)
    return httpx.Client(base_url=base_url, verify=context, timeout=10)

  def _send(self, http: httpx.Client, method: str, path: str, allow: tuple[int, ...] = (), **kwargs) -> httpx.Response:
    try:
      response = http.request(method, path, **kwargs)
    except httpx.TransportError as error:
      raise VclusterUnavailable(f"vcluster unreachable at {http.base_url}: {error}") from error
    if response.is_error and response.status_code not in allow:
      raise VclusterUnavailable(f"vcluster answered {response.status_code} to {method} {path}")
    return response

  def issue(self, obj: dict, sub: str, email: str | None) -> dict:
    """A token for the person's ServiceAccount, created with its binding on first use."""
    identity = identity_name(sub)
    with self._client(obj) as http:
      self._send(http, "POST", "/api/v1/namespaces", allow=(409,), json={
        "apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE, "labels": MANAGED_BY},
      })
      self._send(http, "POST", f"/api/v1/namespaces/{NAMESPACE}/serviceaccounts", allow=(409,), json={
        "apiVersion": "v1", "kind": "ServiceAccount",
        "metadata": {"name": identity, "labels": MANAGED_BY, "annotations": {EMAIL_ANNOTATION: email or ""}},
      })
      self._send(http, "POST", "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings", allow=(409,), json={
        "apiVersion": "rbac.authorization.k8s.io/v1", "kind": "ClusterRoleBinding",
        "metadata": {"name": binding_name(identity), "labels": MANAGED_BY},
        "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": CLUSTER_ROLE},
        "subjects": [{"kind": "ServiceAccount", "name": identity, "namespace": NAMESPACE}],
      })
      response = self._send(http, "POST", f"/api/v1/namespaces/{NAMESPACE}/serviceaccounts/{identity}/token", json={
        "apiVersion": "authentication.k8s.io/v1", "kind": "TokenRequest", "spec": {"expirationSeconds": TOKEN_SECONDS},
      })
    status = response.json()["status"]
    return {"token": status["token"], "expirationTimestamp": status["expirationTimestamp"]}

  def revoke(self, obj: dict, keep: set[str] = frozenset(), only: set[str] | None = None) -> list[str]:
    """Delete the ServiceAccounts (and their tokens) of the people in `only`, or of everyone but `keep`."""
    with self._client(obj) as http:
      response = self._send(http, "GET", f"/api/v1/namespaces/{NAMESPACE}/serviceaccounts", allow=(404,),
                            params={"labelSelector": "app.kubernetes.io/managed-by=platform-api"})
      if response.status_code == 404:
        return []
      names = [item["metadata"]["name"] for item in response.json().get("items", [])]
      revoked = [name for name in names if name not in keep and (only is None or name in only)]
      for name in revoked:
        self._send(http, "DELETE", f"/api/v1/namespaces/{NAMESPACE}/serviceaccounts/{name}", allow=(404,))
        self._send(http, "DELETE", f"/apis/rbac.authorization.k8s.io/v1/clusterrolebindings/{binding_name(name)}", allow=(404,))
    return revoked


def revoke_quietly(credentials, obj: dict, **kwargs) -> None:
  """Revocation after a change already applied: a vcluster that cannot answer only delays it until the
  tokens expire (TOKEN_SECONDS), so it must not fail the request."""
  if credentials is None or not (obj.get("status") or {}).get("kubeconfigData"):
    return
  try:
    revoked = credentials.revoke(obj, **kwargs)
  except VclusterUnavailable as error:
    log.warning("revoking credentials of %s failed, tokens expire on their own: %s", obj["metadata"]["name"], error)
    return
  if revoked:
    log.info("revoked credentials of %s in %s", ", ".join(revoked), obj["metadata"]["name"])
