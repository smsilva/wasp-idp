"""Teams (ADR 0026): Keycloak groups under /teams that the Platform API manages.

Anyone logged in reads them; only platform-admins create, delete and change members. A membership
change reaches the token at the next refresh: `member add` of yourself renews it, anyone else runs
`platform login --refresh`.
"""
from typing import Annotated

import typer

from .. import auth
from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, examples, fail, print_data, print_table, success

app = typer.Typer(help="Teams: who shares environments and owns catalog entities.", no_args_is_help=True)
member_app = typer.Typer(help="Members of a team (platform-admins only).", no_args_is_help=True)
app.add_typer(member_app, name="member")

Email = Annotated[str, typer.Argument(help="E-mail of someone who has logged in to the platform once.")]

TeamName = Annotated[str, typer.Argument(help="Team name (platform team list).")]


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


@app.command("create", epilog=examples("platform team create team-a"))
def create(name: TeamName, output: OutputOption = Format.table):
  """Create a team (platform-admins only)."""
  team = _call(_client().create_team, name)
  if output.data:
    print_data(team, output)
  else:
    success(f"team {name} created")


@app.command("list", epilog=examples("platform team list", "platform team list --output json"))
def list_(output: OutputOption = Format.table):
  """List teams."""
  items = _call(_client().list_teams)
  if output.data:
    print_data(items, output)
    return
  print_table(["NAME"], [[item["name"]] for item in items])


@app.command("get", epilog=examples("platform team get team-a", "platform team get team-a --output json"))
def get(name: TeamName, output: OutputOption = Format.table):
  """Show a team and its members."""
  team = _call(_client().get_team, name)
  if output.data:
    print_data(team, output)
    return
  typer.echo(f"{team['name']}: {len(team['members'])} member(s)")
  if team["members"]:
    print_table(["EMAIL", "USERNAME"], [[member["email"] or "—", member["username"]] for member in team["members"]])


@app.command("delete", epilog=examples("platform team delete team-a"))
def delete(name: TeamName, output: OutputOption = Format.table):
  """Delete a team (platform-admins only)."""
  _call(_client().delete_team, name)
  if output.data:
    print_data({"name": name, "deleted": True}, output)
  else:
    success(f"team {name} deleted")


@member_app.command("add", epilog=examples("platform team member add team-a dev@example.com"))
def member_add(team: TeamName, email: Email, output: OutputOption = Format.table):
  """Add someone to a team; they see it after 'platform login --refresh' (yourself: at once)."""
  client = _client()
  result = _call(client.add_team_member, team, email)
  renewed = _renew_if_yourself(client, team, email)
  if output.data:
    print_data(result, output)
  elif renewed:
    success(f"{email} added to {team} · token renewed, {team} is in it")
  else:
    success(f"{email} added to {team}")


def _renew_if_yourself(client: PlatformClient, team: str, email: str) -> bool:
  """Teams travel in the token: renew it when the caller added themselves, so the team works now."""
  try:
    if (client.me().get("email") or "").lower() != email.lower():
      return False
    auth.refresh_now()
    return team in (client.me().get("teams") or [])
  except (ApiError, auth.AuthError):
    typer.echo(f"  {team} reaches your token after: platform login --refresh", err=True)
    return False


@member_app.command("remove", epilog=examples("platform team member remove team-a dev@example.com"))
def member_remove(team: TeamName, email: Email, output: OutputOption = Format.table):
  """Remove someone from a team."""
  _call(_client().remove_team_member, team, email)
  if output.data:
    print_data({"team": team, "email": email, "removed": True}, output)
  else:
    success(f"{email} removed from {team}")
