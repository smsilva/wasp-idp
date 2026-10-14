import pytest
from typer.testing import CliRunner

from wasp_platform.bootstrap import local
from wasp_platform.cli import app


@pytest.fixture(autouse=True)
def no_install(monkeypatch):
  monkeypatch.setattr(local, "install", lambda **_: pytest.fail("install must not run"))


@pytest.mark.parametrize("value", ["email_not_filled", "", "you@", "@example.com", "a b@example.com", "you@example.com\n"])
def test_admin_must_be_an_email(value):
  result = CliRunner().invoke(app, ["init", "--target", "local", "--admin", value])
  assert result.exit_code == 2
  assert "not an e-mail" in result.output
