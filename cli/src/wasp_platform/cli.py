import typer

from .commands import build, catalog, cloud, environment, registry, scm, team, workload
from .commands.auth import login, logout, whoami
from .commands.init import init

app = typer.Typer(help="platform: the wasp-idp platform CLI.", no_args_is_help=True)
app.command("init")(init)
app.command("login")(login)
app.command("logout")(logout)
app.command("whoami")(whoami)
app.add_typer(environment.app, name="environment")
app.add_typer(catalog.app, name="catalog")
app.add_typer(build.app, name="build")
app.add_typer(workload.app, name="workload")
app.add_typer(team.app, name="team")
app.add_typer(cloud.app, name="cloud")
app.add_typer(scm.app, name="scm")
app.add_typer(registry.app, name="registry")
