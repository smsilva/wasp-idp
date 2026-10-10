"""Only init may reach Docker, k3d or kubectl; everything else goes through the API."""
import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "src" / "wasp_platform"
ALLOWED = {"commands/init.py"}


def imports_bootstrap(path: Path) -> bool:
  for node in ast.walk(ast.parse(path.read_text())):
    if isinstance(node, ast.ImportFrom) and node.module and "bootstrap" in node.module.split("."):
      return True
    if isinstance(node, ast.Import) and any("bootstrap" in alias.name.split(".") for alias in node.names):
      return True
  return False


def test_only_init_and_provider_import_bootstrap():
  offenders = {
    str(path.relative_to(PACKAGE))
    for path in PACKAGE.rglob("*.py")
    if "bootstrap" not in path.relative_to(PACKAGE).parts and imports_bootstrap(path)
  }
  assert offenders <= ALLOWED, f"unexpected bootstrap imports: {offenders - ALLOWED}"


def test_package_does_not_shadow_stdlib_platform():
  import platform

  assert hasattr(platform, "system")
