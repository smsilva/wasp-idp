import typer

from .commands import build, catalog, cloud, environment, registry, scm, status, team, workload
from .commands.auth import login, logout, whoami
from .commands.init import init
from .output import examples

app = typer.Typer(help="platform: the wasp-idp platform CLI.", no_args_is_help=True)
app.command("init", epilog=examples("platform init --generate-file --admin you@example.com", "platform init --edit", "platform init --dry-run", "platform init", "platform init --yes --file init.yaml"))(init)
app.command("login", epilog=examples("platform login", "platform login --use-device-code"))(login)
app.command("logout", epilog=examples("platform logout"))(logout)
app.command("whoami", epilog=examples("platform whoami", "platform whoami --output json"))(whoami)
app.command("status", epilog=examples("platform status", "platform status identity --verbose"))(status.status)
app.add_typer(environment.app, name="environment")
app.add_typer(catalog.app, name="catalog")
app.add_typer(build.app, name="build")
app.add_typer(workload.app, name="workload")
app.add_typer(team.app, name="team")
app.add_typer(cloud.app, name="cloud")
app.add_typer(scm.app, name="scm")
app.add_typer(registry.app, name="registry")
