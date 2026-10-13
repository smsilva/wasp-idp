"""Cloud accounts (ADR 0029): where the platform may create things.

The platform assumes a role in each account from its base credential. `add` returns the trust policy
the account owner applies to that role; the aws_account provider then proves the trust, and `verify`
asks it to check again.
"""
import json
import time
from enum import Enum
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, examples, fail, print_json, print_table, success

app = typer.Typer(help="Cloud resources the platform provisions into.", no_args_is_help=True)
account_app = typer.Typer(help="Cloud accounts: AWS accounts the platform assumes a role in.", no_args_is_help=True)
app.add_typer(account_app, name="account")

ADMIN_GROUP = "platform-admins"

AccountName = Annotated[str, typer.Argument(help="Cloud account name (platform cloud account list).")]


class Vendor(str, Enum):
  aws = "aws"


def _client() -> PlatformClient:
  try:
    return PlatformClient()
  except ApiError as error:
    fail(str(error))


def _call(function, *args):
  try:
    return function(*args)
  except ApiError as error:
    fail(str(error))


def _print_trust_policy(account: dict) -> None:
  policy = account.get("trustPolicy")
  if not policy:
    typer.echo("no trust policy: the platform has no AWS base credential right now")
    return
  typer.echo(f"Trust policy of {account['roleArn']}:")
  typer.echo(json.dumps(policy, indent=2))


def _print_account(account: dict) -> None:
  typer.echo(f"{account['name']}: {account['status']}" + (f" — {account['message']}" if account.get("message") else ""))
  typer.echo(f"  vendor     {account['vendor']}")
  typer.echo(f"  role       {account['roleArn']}")
  typer.echo(f"  account    {account.get('accountId') or '—'}")
  if account.get("regions"):
    typer.echo(f"  regions    {', '.join(account['regions'])}")
  if account.get("callerArn"):
    typer.echo(f"  caller     {account['callerArn']}")
  typer.echo(f"  validated  {account.get('lastValidated') or '—'}")


@account_app.command("add", epilog=examples("platform cloud account add sandbox --role-arn arn:aws:iam::123456789012:role/platform", "platform cloud account add sandbox --role-arn arn:aws:iam::123456789012:role/platform --region us-east-1 --region sa-east-1"))
def add(
  name: Annotated[str, typer.Argument(help="Name for the new cloud account, such as sandbox.")],
  role_arn: Annotated[str, typer.Option("--role-arn", help="IAM role the platform assumes, such as arn:aws:iam::123456789012:role/platform.")],
  vendor: Annotated[Vendor, typer.Option(help="Cloud vendor.")] = Vendor.aws,
  region: Annotated[list[str] | None, typer.Option("--region", help="Region the platform may use; repeat for more.")] = None,
  output: OutputOption = Format.table,
):
  """Register an account and print the trust policy to apply to its role."""
  account = _call(_client().add_cloud_account, name, vendor.value, role_arn, region)
  if output == Format.json:
    print_json(account)
    return
  success(f"cloud account {name} added ({account['status']})")
  _print_trust_policy(account)
  typer.echo(f"Apply it as the trust policy of the role, then run: platform cloud account verify {name} --wait")


@account_app.command("list", epilog=examples("platform cloud account list", "platform cloud account list --output json"))
def list_(output: OutputOption = Format.table):
  """List your cloud accounts (platform-admins see every one)."""
  client = _client()
  items = _call(client.list_cloud_accounts)
  if output == Format.json:
    print_json(items)
    return
  admin = ADMIN_GROUP in _call(client.me).get("groups", [])
  headers = ["NAME", "VENDOR", "ACCOUNT", "STATUS", "VALIDATED", *(["OWNER"] if admin else [])]
  rows = [
    [item["name"], item["vendor"], item.get("accountId") or "—", item["status"], item.get("lastValidated") or "—", *([item.get("owner") or "—"] if admin else [])]
    for item in items
  ]
  print_table(headers, rows)


@account_app.command("get", epilog=examples("platform cloud account get sandbox"))
def get(name: AccountName, output: OutputOption = Format.table):
  """Show a cloud account with its trust policy."""
  account = _call(_client().get_cloud_account, name)
  if output == Format.json:
    print_json(account)
    return
  _print_account(account)
  _print_trust_policy(account)


@account_app.command("verify", epilog=examples("platform cloud account verify sandbox", "platform cloud account verify sandbox --wait --timeout 300"))
def verify(
  name: AccountName,
  wait: Annotated[bool, typer.Option("--wait", help="Wait for the provider's answer.")] = False,
  timeout: Annotated[int, typer.Option(help="Seconds to wait with --wait.")] = 120,
  output: OutputOption = Format.table,
):
  """Ask the provider to check the trust of the account again."""
  client = _client()
  account = _call(client.verify_cloud_account, name)
  deadline = time.monotonic() + timeout
  while wait and account.get("verifyPending"):
    if time.monotonic() > deadline:
      fail(f"{name}: no answer from the cloud account provider after {timeout}s")
    time.sleep(2)
    account = _call(client.get_cloud_account, name)
  if output == Format.json:
    print_json(account)
  elif account["status"] == "ready":
    success(f"{name} ready (account {account['accountId']})")
  elif wait:
    fail(f"{name}: {account['status']}" + (f" — {account['message']}" if account.get("message") else ""))
  else:
    typer.echo(f"{name}: verification requested")


@account_app.command("remove", epilog=examples("platform cloud account remove sandbox"))
def remove(name: AccountName, output: OutputOption = Format.table):
  """Remove a cloud account from the platform (the role stays in the account)."""
  result = _call(_client().remove_cloud_account, name)
  if output == Format.json:
    print_json(result)
  else:
    success(f"cloud account {name} removed")
