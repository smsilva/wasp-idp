"""The Pod Security Standard baseline of each environment (#414, ADR 0041) inside its vcluster.

The guard is the same ValidatingAdmissionPolicy on the host (deploy/pod-security.yaml, applied by
`platform init`), bound to the pods the vcluster syncs: users are cluster-admin in the vcluster and can
delete this copy. The copy only makes a refused pod fail at apply, instead of staying Pending in the vcluster
while the syncer cannot create it on the host. It binds to every pod of the vcluster.
"""
import hashlib
import os

import yaml
from kubernetes import config, dynamic

from .mesh import SERVER, in_cluster

POLICY = os.environ.get("POD_SECURITY_POLICY", "/manifests/pod-security.yaml")
MANAGER = "platform-local-vcluster"


def policy(path: str = POLICY) -> dict:
  with open(path) as file:
    return next(d for d in yaml.safe_load_all(file) if d and d["kind"] == "ValidatingAdmissionPolicy")


def vcluster_objects(path: str = POLICY) -> list[dict]:
  obj = policy(path)
  name = obj["metadata"]["name"]
  binding = {
    "apiVersion": obj["apiVersion"],
    "kind": "ValidatingAdmissionPolicyBinding",
    "metadata": {"name": name, "labels": {"app.kubernetes.io/managed-by": MANAGER}},
    "spec": {"policyName": name, "validationActions": ["Deny"]},
  }
  obj["metadata"]["labels"] = {"app.kubernetes.io/managed-by": MANAGER}
  return [obj, binding]


def wanted(path: str = POLICY) -> str:
  """The version of the policy (status.podSecurity): a new one reaches the environments already created."""
  with open(path, "rb") as file:
    return hashlib.sha256(file.read()).hexdigest()[:12]


class PodSecurity:
  def __init__(self, path: str = POLICY, server: str = SERVER):
    self.path, self.server = path, server

  def wanted(self) -> str:
    return wanted(self.path)

  def install(self, name: str, kubeconfig: str) -> None:
    api = dynamic.DynamicClient(config.new_client_from_config_dict(in_cluster(kubeconfig, name, self.server)))
    for obj in vcluster_objects(self.path):
      resource = api.resources.get(api_version=obj["apiVersion"], kind=obj["kind"])
      api.server_side_apply(resource, body=obj, field_manager=MANAGER, force_conflicts=True)
