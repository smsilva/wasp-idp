from datetime import datetime, timezone

import pytest

from crossplane_aws_provider.reconciler import (
  BASE_SECRET,
  CIDR,
  CROSSPLANE_NAMESPACE,
  FINALIZER,
  MANAGED_BY,
  NotManaged,
  Reconciler,
  provider_config,
  vpc,
  vpc_name,
)

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
ROLE = "arn:aws:iam::123456789012:role/platform"


class FakeEnvironments:
  def __init__(self):
    self.finalizers, self.statuses = {}, {}

  def set_finalizers(self, name, finalizers):
    self.finalizers[name] = finalizers

  def patch_status(self, name, status):
    self.statuses.setdefault(name, []).append(status)


class FakeCrossplane:
  def __init__(self):
    self.configs, self.vpcs, self.deleted_vpcs = {}, {}, []

  def provider_configs(self):
    return list(self.configs)

  def apply_provider_config(self, body):
    self.configs[body["metadata"]["name"]] = body

  def delete_provider_config(self, name):
    self.configs.pop(name, None)

  def get_vpc(self, name):
    return self.vpcs.get(name)

  def create_vpc(self, body):
    self.vpcs[body["metadata"]["name"]] = body

  def delete_vpc(self, name):
    self.deleted_vpcs.append(name)
    self.vpcs[name]["metadata"]["deletionTimestamp"] = "2026-10-13T12:00:00Z"


def account(name="nonprod-aws", ready=True, regions=("us-east-1", "sa-east-1")):
  return {
    "metadata": {"name": name, "uid": f"uid-{name}"},
    "spec": {"vendor": "aws", "aws": {"roleArn": ROLE, "externalId": "external-id", "regions": list(regions)}},
    "status": {"conditions": [{"type": "Ready", "status": "True" if ready else "False", "reason": "Verified" if ready else "TrustNotEstablished"}]},
  }


def environment(name="demo", account_name="nonprod-aws", finalizers=None, deleting=False, status=None):
  metadata = {"name": name, "finalizers": finalizers if finalizers is not None else [FINALIZER]}
  if account_name:
    metadata["annotations"] = {"platform.wasp.silvios.me/cloud-account-uid": f"uid-{account_name}"}
  if deleting:
    metadata["deletionTimestamp"] = "2026-10-13T12:00:00Z"
  spec = {"profile": "ephemeral"}
  if account_name:
    spec["cloudAccount"] = account_name
  return {"metadata": metadata, "spec": spec, "status": status or {}}


def vpc_with(synced=None, ready=None, vpc_id=None):
  conditions = []
  if synced:
    conditions.append({"type": "Synced", "status": synced[0], "reason": synced[1], "message": synced[2] if len(synced) > 2 else ""})
  if ready:
    conditions.append({"type": "Ready", "status": ready, "reason": "Available" if ready == "True" else "Creating"})
  status = {"conditions": conditions}
  if vpc_id:
    status["atProvider"] = {"id": vpc_id}
  return {"metadata": {"name": "env-demo", "labels": {"app.kubernetes.io/managed-by": MANAGED_BY, "platform.wasp.silvios.me/environment": "demo"}}, "status": status}


@pytest.fixture
def stores():
  return FakeEnvironments(), FakeCrossplane()


def reconciler(stores):
  return Reconciler(stores[0], stores[1], now=lambda: NOW)


def last_ready(stores, name="demo"):
  return stores[0].statuses[name][-1]["conditions"][0]


# The ProviderConfig of each account (ADR 0029: generated from the CloudAccount).

def test_a_ready_account_gets_a_provider_config(stores):
  reconciler(stores).sync_accounts([account(), account("pending", ready=False)])
  assert list(stores[1].configs) == ["nonprod-aws"]
  body = stores[1].configs["nonprod-aws"]
  assert body["metadata"]["labels"] == {"app.kubernetes.io/managed-by": MANAGED_BY}
  assert body["spec"]["credentials"] == {"source": "Secret", "secretRef": {"namespace": CROSSPLANE_NAMESPACE, "name": BASE_SECRET, "key": "creds"}}
  assert body["spec"]["assumeRoleChain"] == [{"roleARN": ROLE, "externalID": "external-id"}]


def test_an_account_that_stops_being_ready_keeps_its_provider_config(stores):
  # Revalidation can fail for a while; the resources already there keep being reconciled.
  stores[1].configs["nonprod-aws"] = provider_config(account())
  reconciler(stores).sync_accounts([account(ready=False)])
  assert list(stores[1].configs) == ["nonprod-aws"]


def test_a_removed_account_loses_its_provider_config(stores):
  stores[1].configs["gone"] = provider_config(account("gone"))
  reconciler(stores).sync_accounts([account()])
  assert sorted(stores[1].configs) == ["nonprod-aws"]


# One VPC per environment in an account.

def test_an_environment_without_account_is_not_ours(stores):
  reconciler(stores).reconcile(environment(account_name=None, finalizers=[]), {})
  assert stores[0].finalizers == {} and stores[0].statuses == {} and stores[1].vpcs == {}


def test_first_pass_adds_the_finalizer_and_creates_the_vpc(stores):
  reconciler(stores).reconcile(environment(finalizers=["other"]), {"nonprod-aws": account()})
  assert stores[0].finalizers["demo"] == ["other", FINALIZER]
  body = stores[1].vpcs[vpc_name("demo")]
  assert body["spec"]["providerConfigRef"] == {"name": "nonprod-aws"}
  assert body["spec"]["forProvider"]["region"] == "us-east-1"
  assert body["spec"]["forProvider"]["cidrBlock"] == CIDR
  assert body["spec"]["forProvider"]["tags"]["platform.wasp.silvios.me/environment"] == "demo"
  assert body["metadata"]["labels"]["platform.wasp.silvios.me/environment"] == "demo"
  ready = last_ready(stores)
  assert (ready["status"], ready["reason"]) == ("False", "Provisioning")
  assert stores[0].statuses["demo"][-1]["cloud"] == {"vendor": "aws", "region": "us-east-1"}


def test_an_account_not_ready_creates_nothing(stores):
  reconciler(stores).reconcile(environment(), {"nonprod-aws": account(ready=False)})
  assert stores[1].vpcs == {}
  assert last_ready(stores)["reason"] == "CloudAccountNotReady"
  reconciler(stores).reconcile(environment(), {})
  assert "not found" in last_ready(stores)["message"]


def test_an_account_without_region_creates_nothing(stores):
  # The API refuses it on create; the account is checked again here, in case it was registered before.
  reconciler(stores).reconcile(environment(), {"nonprod-aws": account(regions=())})
  assert stores[1].vpcs == {}
  assert last_ready(stores)["reason"] == "NoRegion"


def test_vpc_ready_makes_the_environment_ready(stores):
  stores[1].vpcs["env-demo"] = vpc_with(synced=("True", "ReconcileSuccess"), ready="True", vpc_id="vpc-0abc")
  stores[1].vpcs["env-demo"]["spec"] = {"forProvider": {"region": "us-east-1"}}
  reconciler(stores).reconcile(environment(), {"nonprod-aws": account()})
  status = stores[0].statuses["demo"][-1]
  assert status["cloud"] == {"vendor": "aws", "region": "us-east-1", "vpcId": "vpc-0abc"}
  ready = status["conditions"][0]
  assert (ready["status"], ready["reason"]) == ("True", "CloudReady")
  assert "vpc-0abc" in ready["message"] and "nonprod-aws" in ready["message"]


def test_vpc_still_creating_keeps_provisioning(stores):
  stores[1].vpcs["env-demo"] = vpc_with(synced=("True", "ReconcileSuccess"), ready="False")
  stores[1].vpcs["env-demo"]["spec"] = {"forProvider": {"region": "us-east-1"}}
  reconciler(stores).reconcile(environment(), {"nonprod-aws": account()})
  assert last_ready(stores)["reason"] == "Provisioning"


def test_vpc_not_synced_is_a_failure_with_its_message(stores):
  stores[1].vpcs["env-demo"] = vpc_with(synced=("False", "ReconcileError", "cannot assume role: AccessDenied"))
  stores[1].vpcs["env-demo"]["spec"] = {"forProvider": {"region": "us-east-1"}}
  reconciler(stores).reconcile(environment(), {"nonprod-aws": account()})
  ready = last_ready(stores)
  assert (ready["status"], ready["reason"]) == ("False", "ProvisioningFailed")
  assert "AccessDenied" in ready["message"]


@pytest.mark.parametrize("vpc_id, ready", [("vpc-0abc", "True"), (None, "False")])
def test_an_unchanged_condition_is_not_patched_again(stores, vpc_id, ready):
  stores[1].vpcs["env-demo"] = vpc_with(synced=("True", "ReconcileSuccess"), ready=ready, vpc_id=vpc_id)
  stores[1].vpcs["env-demo"]["spec"] = {"forProvider": {"region": "us-east-1"}}
  reconciler(stores).reconcile(environment(), {"nonprod-aws": account()})
  status = stores[0].statuses["demo"][-1]
  reconciler(stores).reconcile(environment(status=status), {"nonprod-aws": account()})
  assert len(stores[0].statuses["demo"]) == 1


# Delete: the VPC goes first, then the finalizer.

def test_delete_removes_the_vpc_and_waits_for_it(stores):
  stores[1].vpcs["env-demo"] = vpc_with(ready="True", vpc_id="vpc-0abc")
  reconciler(stores).reconcile(environment(deleting=True, finalizers=["other", FINALIZER]), {})
  assert stores[1].deleted_vpcs == ["env-demo"]
  assert "demo" not in stores[0].finalizers
  # Still there, being deleted by Crossplane: no second delete, the finalizer stays.
  reconciler(stores).reconcile(environment(deleting=True, finalizers=["other", FINALIZER]), {})
  assert stores[1].deleted_vpcs == ["env-demo"]
  del stores[1].vpcs["env-demo"]
  reconciler(stores).reconcile(environment(deleting=True, finalizers=["other", FINALIZER]), {})
  assert stores[0].finalizers["demo"] == ["other"]


def test_delete_without_our_finalizer_does_nothing(stores):
  reconciler(stores).reconcile(environment(deleting=True, finalizers=[]), {})
  assert stores[0].finalizers == {} and stores[1].deleted_vpcs == []


def test_a_failure_becomes_the_condition(stores):
  class Broken(FakeCrossplane):
    def create_vpc(self, body):
      raise RuntimeError("the server could not find the requested resource")

  stores = (stores[0], Broken())
  reconciler(stores).reconcile(environment(), {"nonprod-aws": account()})
  ready = last_ready(stores)
  assert ready["reason"] == "ProvisioningFailed"
  assert "requested resource" in ready["message"]


def test_vpc_names_follow_the_environment():
  assert vpc_name("demo") == "env-demo"
  assert vpc(environment(), account())["metadata"]["name"] == "env-demo"


# Names come from users: what this provider did not write is never changed nor deleted.

def test_a_provider_config_that_is_not_ours_holds_back_only_its_account(stores):
  class Guarded(FakeCrossplane):
    def apply_provider_config(self, body):
      if body["metadata"]["name"] == "network":
        raise NotManaged("ProviderConfig network exists and was not written by crossplane-aws-provider")
      super().apply_provider_config(body)

  stores = (stores[0], Guarded())
  reconciler(stores).sync_accounts([account("network"), account()])
  assert list(stores[1].configs) == ["nonprod-aws"]


def test_a_vpc_that_is_not_ours_is_never_adopted_nor_deleted(stores):
  foreign = vpc_with(synced=("True", "ReconcileSuccess"), ready="True", vpc_id="vpc-0abc")
  foreign["metadata"]["labels"] = {}
  foreign["spec"] = {"forProvider": {"region": "us-east-1"}}
  stores[1].vpcs["env-demo"] = foreign
  reconciler(stores).reconcile(environment(), {"nonprod-aws": account()})
  ready = last_ready(stores)
  assert (ready["reason"], "not created for this environment" in ready["message"]) == ("ProvisioningFailed", True)
  reconciler(stores).reconcile(environment(deleting=True, finalizers=[FINALIZER]), {})
  assert stores[1].deleted_vpcs == []
  assert stores[0].finalizers["demo"] == []


@pytest.mark.parametrize("annotations", [{}, {"platform.wasp.silvios.me/cloud-account-uid": "uid-of-an-earlier-account"}])
def test_only_the_account_the_api_authorized(stores, annotations):
  # Written around the API, or the account was removed and registered again under the same name.
  obj = environment()
  obj["metadata"]["annotations"] = annotations
  reconciler(stores).reconcile(obj, {"nonprod-aws": account()})
  assert stores[1].vpcs == {}
  ready = last_ready(stores)
  assert (ready["reason"], "not the one authorized" in ready["message"]) == ("ProvisioningFailed", True)
