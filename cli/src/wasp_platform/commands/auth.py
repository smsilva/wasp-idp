from typing import Annotated

import typer

from .. import auth
from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, fail, print_json, success


def login(
  use_device_code: Annotated[bool, typer.Option("--use-device-code", help="Sign in from another device (SSH, containers, no browser).")] = False,
):
  """Sign in to the platform with your Google account."""
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


def logout():
  """Sign out and revoke the session."""
  credentials = auth.load_credentials()
  if credentials and credentials.get("refresh_token"):
    try:
      auth.Oidc().revoke(credentials["refresh_token"])
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
  if output == Format.json:
    print_json(me)
  else:
    typer.echo(_who(me))


def _who(me: dict) -> str:
  groups = ", ".join(me.get("groups") or []) or "no groups"
  return f"{me.get('email') or me['sub']} ({groups})"
