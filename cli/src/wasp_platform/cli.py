import typer

from .commands import environment
from .commands.auth import login, logout, whoami
from .commands.init import init

app = typer.Typer(help="platform: the wasp-idp platform CLI.", no_args_is_help=True)
app.command("init")(init)
app.command("login")(login)
app.command("logout")(logout)
app.command("whoami")(whoami)
app.add_typer(environment.app, name="environment")
