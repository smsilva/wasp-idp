"""Environments in an AWS CloudAccount, through Crossplane (ADR 0032).

1. Each CloudAccount that is Ready gets a ProviderConfig with its name (ADR 0029): the platform base
   credential, then AssumeRole into the account's role with its ExternalId.
2. Each Environment with spec.cloudAccount gets one VPC in the account's first region, as a Crossplane
   managed resource; its Synced/Ready conditions become the Ready condition of the Environment (ADR 0022).
3. Deleting the Environment deletes the VPC first: the finalizer goes only once Crossplane removed it.

The expiry (spec.expiresAt) is enforced by local_vcluster for every environment: here it is only a delete.
"""
import logging
from datetime import datetime, timezone

GROUP = "platform.wasp.silvios.me"
FINALIZER = f"{GROUP}/crossplane-aws"
ENVIRONMENT_LABEL = f"{GROUP}/environment"
MANAGED_BY = "crossplane-aws-provider"
# Written by `platform init --with-crossplane` from Secret aws-base-credential of platform-system.
CROSSPLANE_NAMESPACE = "crossplane-system"
BASE_SECRET = "aws-base-credential"
# Every environment gets the same range: VPCs that never peer may overlap.
CIDR = "10.0.0.0/16"

log = logging.getLogger("crossplane-aws-provider")


def utcnow() -> datetime:
  return datetime.now(timezone.utc)


def condition(obj: dict, kind: str) -> dict | None:
  return next((c for c in (obj.get("status") or {}).get("conditions", []) if c.get("type") == kind), None)


def is_ready(obj: dict) -> bool:
  ready = condition(obj, "Ready")
  return bool(ready and ready.get("status") == "True")


class NotManaged(Exception):
  """An object with the name this provider wants, written by someone else: it is left alone."""


def managed(obj: dict, environment: str | None = None) -> bool:
  """Written by this provider and, for a VPC, for this environment. Names come from users (accounts,
  environments): a match by name alone must never let the provider change or delete what is not its own."""
  labels = (obj.get("metadata") or {}).get("labels") or {}
  return labels.get("app.kubernetes.io/managed-by") == MANAGED_BY and (environment is None or labels.get(ENVIRONMENT_LABEL) == environment)


def vpc_name(environment: str) -> str:
  return f"env-{environment}"


def provider_config(account: dict) -> dict:
  aws = account["spec"]["aws"]
  return {
    "apiVersion": "aws.upbound.io/v1beta1",
    "kind": "ProviderConfig",
    "metadata": {"name": account["metadata"]["name"], "labels": {"app.kubernetes.io/managed-by": MANAGED_BY}},
    "spec": {
      "credentials": {"source": "Secret", "secretRef": {"namespace": CROSSPLANE_NAMESPACE, "name": BASE_SECRET, "key": "creds"}},
      "assumeRoleChain": [{"roleARN": aws["roleArn"], "externalID": aws["externalId"]}],
    },
  }


def vpc(environment: dict, account: dict) -> dict:
  name = environment["metadata"]["name"]
  return {
    "apiVersion": "ec2.aws.upbound.io/v1beta1",
    "kind": "VPC",
    "metadata": {"name": vpc_name(name), "labels": {"app.kubernetes.io/managed-by": MANAGED_BY, ENVIRONMENT_LABEL: name}},
    "spec": {
      "forProvider": {
        "region": account["spec"]["aws"]["regions"][0],
        "cidrBlock": CIDR,
        "enableDnsSupport": True,
        "enableDnsHostnames": True,
        "tags": {"Name": vpc_name(name), ENVIRONMENT_LABEL: name, "managed-by": "wasp-platform"},
      },
      "providerConfigRef": {"name": account["metadata"]["name"]},
    },
  }


class Reconciler:
  def __init__(self, environments, crossplane, now=utcnow):
    self.environments = environments
    self.crossplane = crossplane
    self.now = now

  def sync_accounts(self, accounts: list[dict]) -> None:
    """A ProviderConfig per Ready account. One that stops being Ready keeps it (revalidation may fail for a
    while); one that is gone loses it. Crossplane keeps it until no managed resource uses it."""
    names = {account["metadata"]["name"] for account in accounts}
    for account in accounts:
      if is_ready(account):
        try:
          self.crossplane.apply_provider_config(provider_config(account))
        except Exception:  # one account must not hold back the others
          log.exception("ProviderConfig of cloud account %s not applied", account["metadata"]["name"])
    for name in self.crossplane.provider_configs():
      if name not in names:
        log.info("cloud account %s is gone, deleting its ProviderConfig", name)
        self.crossplane.delete_provider_config(name)

  def reconcile(self, obj: dict, accounts: dict[str, dict]) -> None:
    if not (obj.get("spec") or {}).get("cloudAccount"):
      return
    name = obj["metadata"]["name"]
    try:
      self._reconcile(obj, accounts)
    except Exception as error:  # keep the loop alive; the condition tells the user what failed
      log.exception("reconcile %s failed", name)
      if not obj["metadata"].get("deletionTimestamp"):
        self._report(obj, "False", "ProvisioningFailed", str(error)[:500])

  def _reconcile(self, obj: dict, accounts: dict[str, dict]) -> None:
    metadata = obj["metadata"]
    name = metadata["name"]
    finalizers = metadata.get("finalizers") or []

    if metadata.get("deletionTimestamp"):
      if FINALIZER not in finalizers:
        return
      found = self.crossplane.get_vpc(vpc_name(name))
      if found is None or not managed(found, name):
        # Someone else's VPC object with this name is never deleted.
        self.environments.set_finalizers(name, [f for f in finalizers if f != FINALIZER])
        log.info("environment %s removed", name)
      elif not found["metadata"].get("deletionTimestamp"):
        log.info("deleting vpc %s", vpc_name(name))
        self.crossplane.delete_vpc(vpc_name(name))
      return

    if FINALIZER not in finalizers:
      self.environments.set_finalizers(name, [*finalizers, FINALIZER])

    account_name = obj["spec"]["cloudAccount"]
    found = self.crossplane.get_vpc(vpc_name(name))
    if found is None:
      account = accounts.get(account_name)
      if account is None:
        return self._report(obj, "False", "CloudAccountNotReady", f"cloud account {account_name} not found")
      if not is_ready(account):
        return self._report(obj, "False", "CloudAccountNotReady", f"cloud account {account_name} is not ready: platform cloud account get {account_name}")
      if not account["spec"]["aws"].get("regions"):
        return self._report(obj, "False", "NoRegion", f"cloud account {account_name} has no region")
      body = vpc(obj, account)
      log.info("creating vpc %s in %s (account %s)", vpc_name(name), body["spec"]["forProvider"]["region"], account_name)
      self.crossplane.create_vpc(body)
      found = body

    elif not managed(found, name):
      return self._report(obj, "False", "ProvisioningFailed", f"vpc {vpc_name(name)} exists and was not created for this environment")

    region = found["spec"]["forProvider"]["region"]
    vpc_id = ((found.get("status") or {}).get("atProvider") or {}).get("id")
    # Without None values: a merge patch drops them, and the next pass would see a change.
    cloud = {"vendor": "aws", "region": region, **({"vpcId": vpc_id} if vpc_id else {})}
    synced = condition(found, "Synced")
    if synced and synced.get("status") == "False":
      return self._report(obj, "False", "ProvisioningFailed", (synced.get("message") or synced.get("reason") or "")[:500], cloud)
    if is_ready(found) and vpc_id:
      return self._report(obj, "True", "CloudReady", f"vpc {vpc_id} in {region}, cloud account {account_name}", cloud)
    self._report(obj, "False", "Provisioning", f"creating vpc {vpc_name(name)} in {region}", cloud)

  def _report(self, obj: dict, status: str, reason: str, message: str, cloud: dict | None = None) -> None:
    """Patch only on a change: lastTransitionTime marks a transition, and every patch wakes the watchers."""
    current = condition(obj, "Ready") or {}
    if (current.get("status"), current.get("reason"), current.get("message")) == (status, reason, message) and (obj.get("status") or {}).get("cloud") == cloud:
      return
    patch = {"conditions": [{
      "type": "Ready",
      "status": status,
      "reason": reason,
      "message": message,
      "lastTransitionTime": self.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }]}
    if cloud is not None:
      patch["cloud"] = cloud
    self.environments.patch_status(obj["metadata"]["name"], patch)
