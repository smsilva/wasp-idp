import pytest

from wasp_platform.bootstrap import local


@pytest.mark.parametrize(("output", "expected"), [
  ("k3d version v5.9.0\nk3s version v1.35.5-k3s1 (default)\n", (5, 9, 0)),
  ("k3d version v5.7.4\nk3s version v1.30.4-k3s1 (default)\n", (5, 7, 4)),
  ("", None),
  ("command not found", None),
])
def test_k3d_version(output, expected):
  assert local.k3d_version(output) == expected


@pytest.mark.parametrize(("output", "ok"), [
  ("k3d version v5.9.0\n", True),
  ("k3d version v5.10.1\n", True),
  ("k3d version v5.7.4\n", False),
  ("garbage", False),
])
def test_check_k3d(monkeypatch, output, ok):
  monkeypatch.setattr(local.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": output})())
  if ok:
    local.check_k3d()
  else:
    with pytest.raises(local.BootstrapError, match="5.9.0 or newer"):
      local.check_k3d()
