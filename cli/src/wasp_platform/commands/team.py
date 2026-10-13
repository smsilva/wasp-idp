"""Teams (ADR 0026): Keycloak groups under /teams that the Platform API manages.

Anyone logged in reads them; only platform-admins create, delete and change members. A membership
change reaches the `groups` claim at the next token, so the member runs `platform login` again.
"""
from typing import Annotated

import typer

from ..client import ApiError, PlatformClient
from ..output import Format, OutputOption, examples, fail, print_json, print_table, success

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
  if output == Format.json:
    print_json(team)
  else:
    success(f"team {name} created")


@app.command("list", epilog=examples("platform team list", "platform team list --output json"))
def list_(output: OutputOption = Format.table):
  """List teams."""
  items = _call(_client().list_teams)
  if output == Format.json:
    print_json(items)
    return
  print_table(["NAME"], [[item["name"]] for item in items])


@app.command("get", epilog=examples("platform team get team-a", "platform team get team-a --output json"))
def get(name: TeamName, output: OutputOption = Format.table):
  """Show a team and its members."""
  team = _call(_client().get_team, name)
  if output == Format.json:
    print_json(team)
    return
  typer.echo(f"{team['name']}: {len(team['members'])} member(s)")
  if team["members"]:
    print_table(["EMAIL", "USERNAME"], [[member["email"] or "—", member["username"]] for member in team["members"]])


@app.command("delete", epilog=examples("platform team delete team-a"))
def delete(name: TeamName, output: OutputOption = Format.table):
  """Delete a team (platform-admins only)."""
  _call(_client().delete_team, name)
  if output == Format.json:
    print_json({"name": name, "deleted": True})
  else:
    success(f"team {name} deleted")


@member_app.command("add", epilog=examples("platform team member add team-a dev@example.com"))
def member_add(team: TeamName, email: Email, output: OutputOption = Format.table):
  """Add someone to a team; they see it after the next 'platform login'."""
  result = _call(_client().add_team_member, team, email)
  if output == Format.json:
    print_json(result)
  else:
    success(f"{email} added to {team}")


@member_app.command("remove", epilog=examples("platform team member remove team-a dev@example.com"))
def member_remove(team: TeamName, email: Email, output: OutputOption = Format.table):
  """Remove someone from a team."""
  _call(_client().remove_team_member, team, email)
  if output == Format.json:
    print_json({"team": team, "email": email, "removed": True})
  else:
    success(f"{email} removed from {team}")
