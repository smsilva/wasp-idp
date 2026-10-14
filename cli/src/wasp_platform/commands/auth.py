from typing import Annotated

import typer

from .. import auth, config
from ..bootstrap import local
from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_data, success


def login(
  use_device_code: Annotated[bool, typer.Option("--use-device-code", help="Sign in from another device (SSH, containers, no browser).")] = False,
  refresh: Annotated[bool, typer.Option("--refresh", help="Renew the token without the browser, so a team joined since the last login shows; signs in again if the session expired.")] = False,
  # Local test identities (#179): hidden, they exist only in the realm of the local target.
  test_user: Annotated[bool, typer.Option("--test-user", hidden=True)] = False,
  test_admin: Annotated[bool, typer.Option("--test-admin", hidden=True)] = False,
  test_member: Annotated[bool, typer.Option("--test-member", hidden=True)] = False,
):
  """Sign in to the platform with your Google account."""
  if refresh and (test_user or test_admin or test_member):
    raise typer.BadParameter("--refresh renews the current session; it does not go with a test identity", param_hint="--refresh")
  if refresh:
    try:
      tokens = auth.refresh_now()
    except auth.AuthError as error:
      typer.echo(f"{error}; signing in again", err=True)
    else:
      _logged_in(tokens)
      return
  if test_user or test_admin or test_member:
    _login_test_user(local.SMOKE_ADMIN if test_admin else local.SMOKE_MEMBER if test_member else local.SMOKE_USER)
    return
  try:
    oidc = auth.Oidc()
    if use_device_code:
      def show(user_code: str, url: str) -> None:
        typer.echo(f"Open {url}")
        typer.echo(f"and confirm the code {user_code}")
      tokens = oidc.login_device(show)
    else:
      typer.echo("Opening the browser to sign in …")
      tokens = oidc.login_browser()
    auth.save_credentials(tokens)
    me = PlatformClient(token=lambda: tokens["access_token"]).me()
  except (auth.AuthError, ApiError) as error:
    fail(str(error))
  success(f"Logged in as {_who(me)}")


def _logged_in(tokens: dict) -> None:
  try:
    me = PlatformClient(token=lambda: tokens["access_token"]).me()
  except ApiError as error:
    fail(str(error))
  success(f"Logged in as {_who(me)}")


def _login_test_user(username: str) -> None:
  """Password grant on the local test client: the CLI flow without a browser (scripts/test/cli-smoke)."""
  flag = {local.SMOKE_ADMIN: "--test-admin", local.SMOKE_MEMBER: "--test-member"}.get(username, "--test-user")
  if config.load().get("target") != "local":
    fail(f"{flag} is only supported on the local target")
  try:
    password = local.smoke_password(username)
    tokens = auth.Oidc(client_id=local.SMOKE_CLIENT_ID).login_password(username, password)
    auth.save_credentials(tokens, client_id=local.SMOKE_CLIENT_ID)
    me = PlatformClient(token=lambda: tokens["access_token"]).me()
  except (local.BootstrapError, auth.AuthError, ApiError) as error:
    fail(str(error))
  success(f"Logged in as {_who(me)}")


def logout():
  """Sign out and revoke the session."""
  credentials = auth.load_credentials()
  if credentials and credentials.get("refresh_token"):
    try:
      client_id = credentials.get("client_id")
      oidc = auth.Oidc(client_id=client_id) if client_id else auth.Oidc()
      oidc.revoke(credentials["refresh_token"])
    except auth.AuthError:
      pass
  auth.delete_credentials()
  success("Logged out")


def whoami(output: OutputOption = Format.table):
  """Show who the Platform API sees you as."""
  try:
    me = PlatformClient().me()
  except ApiError as error:
    fail(str(error))
  if output.data:
    print_data(me, output)
  else:
    typer.echo(_who(me))


def _who(me: dict) -> str:
  groups = ", ".join(me.get("groups") or []) or "no groups"
  return f"{me.get('email') or me['sub']} ({groups})"
