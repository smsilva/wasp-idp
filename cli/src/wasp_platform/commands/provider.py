import typer

from ..bootstrap import local
from ..commands.init import Target
from ..output import fail

app = typer.Typer(help="Providers that satisfy platform capabilities.", no_args_is_help=True)


@app.command("run")
def run(target: Target = typer.Option(..., help="Target whose provider runs in the foreground.")):
  """Run the environment provider of a target in the foreground."""
  if target != Target.local:
    fail(f"target '{target.value}' is not supported yet")
  try:
    local.run_provider()
  except local.BootstrapError as error:
    fail(str(error))
