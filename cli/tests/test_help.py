"""Every command explains its arguments and shows how to call it (#408)."""
import shlex

from typer.main import TyperArgument, get_command
from typer.testing import CliRunner

from wasp_platform.cli import app


def commands(command=None, path=()):
  command = command or get_command(app)
  if hasattr(command, "commands"):
    for name, sub in command.commands.items():
      yield from commands(sub, (*path, name))
  else:
    yield " ".join(path), command


def test_every_argument_has_help():
  missing = [f"{path} <{param.name}>" for path, command in commands() for param in command.params
             if isinstance(param, TyperArgument) and not param.help]
  assert missing == []


def test_every_command_has_examples():
  missing = [path for path, command in commands() if not (command.epilog or "").startswith("Examples:")]
  assert missing == []


def test_examples_call_the_command_itself():
  wrong = [path for path, command in commands() if command.epilog
           for line in command.epilog.splitlines()[2:] if not line.strip().startswith(f"$ platform {path}")]
  assert wrong == []


def test_examples_parse():
  """Each example is a valid call: known options, required arguments present."""
  wrong = []
  for path, command in commands():
    for line in (command.epilog or "").splitlines()[2:]:
      words = shlex.split(line.strip().removeprefix("$ "))[1 + len(path.split()):]
      try:
        command.make_context(path, words)
      except Exception as error:
        wrong.append(f"{line.strip()}: {error}")
  assert wrong == []


def test_examples_show_in_help():
  result = CliRunner().invoke(app, ["build", "get", "--help"])
  assert "Examples:" in result.output
  assert "$ platform build get" in result.output


def test_output_has_a_short_option():
  """-o works wherever --output picks a format (not on template render, where --output is a folder)."""
  missing = [path for path, command in commands() for param in command.params
             if param.name == "output" and "--output" in param.opts and getattr(param.type, "choices", None) and "-o" not in param.opts]
  assert missing == []
