import typer

from .commands import environment, provider
from .commands.init import init

app = typer.Typer(help="platform: the wasp-idp platform CLI.", no_args_is_help=True)
app.command("init")(init)
app.add_typer(environment.app, name="environment")
app.add_typer(provider.app, name="provider")
