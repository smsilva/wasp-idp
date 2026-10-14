import pytest

from wasp_platform.bootstrap.settings import SettingsError, from_file, resolve, to_file

FILE = "~/.config/platform/init.yaml"


def write(tmp_path, text):
  path = tmp_path / "init.yaml"
  path.write_text(text)
  return path


def values(settings):
  return {name: (setting.value, setting.source) for name, setting in settings.items()}


def test_defaults_without_flags_file_or_cluster():
  assert values(resolve({}, {}, None, {})) == {
    "target": ("local", "default"),
    "admins": ([], "default"),
    "aws_profile": (None, "default"),
    "with_crossplane": (False, "default"),
  }


def test_flag_wins_over_file_and_file_over_cluster():
  settings = resolve(
    {"admins": ["flag@example.org"], "with_crossplane": None},
    {"admins": ["file@example.org"], "aws_profile": "dev"},
    FILE,
    {"admins": ["cluster@example.org"], "with_crossplane": True},
  )
  assert values(settings) == {
    "target": ("local", "default"),
    "admins": (["flag@example.org"], "flag"),
    "aws_profile": ("dev", FILE),
    "with_crossplane": (True, "cluster"),
  }


def test_file_is_read_with_camel_case_keys(tmp_path):
  path = write(tmp_path, """
apiVersion: platform.wasp.silvios.me/v1alpha1
kind: InitConfig
target: local
admins:
  - you@example.org
  - other@example.org
awsProfile: dev
withCrossplane: true
""")
  assert from_file(path) == {"target": "local", "admins": ["you@example.org", "other@example.org"], "aws_profile": "dev", "with_crossplane": True}


def test_generated_file_reads_back(tmp_path):
  settings = resolve({"admins": ["you@example.org"]}, {}, None, {})
  path = write(tmp_path, to_file(settings))
  assert from_file(path) == {"target": "local", "admins": ["you@example.org"], "aws_profile": None, "with_crossplane": False}


def test_empty_flag_list_falls_back_to_the_file():
  settings = resolve({"admins": []}, {"admins": ["file@example.org"]}, FILE, {})
  assert values(settings)["admins"] == (["file@example.org"], FILE)


@pytest.mark.parametrize("text, error", [
  ("kind: InitConfig\n", "apiVersion"),
  ("apiVersion: platform.wasp.silvios.me/v1alpha1\nkind: Other\n", "kind"),
  ("apiVersion: platform.wasp.silvios.me/v1alpha1\nkind: InitConfig\nadmin: you@example.org\n", "admin"),
  ("apiVersion: platform.wasp.silvios.me/v1alpha1\nkind: InitConfig\nadmins: [email_not_filled]\n", "not an e-mail"),
  ("apiVersion: platform.wasp.silvios.me/v1alpha1\nkind: InitConfig\nadmins: you@example.org\n", "list"),
  ("apiVersion: platform.wasp.silvios.me/v1alpha1\nkind: InitConfig\nadmins: [\"a@b.org,c@d.org\"]\n", "not an e-mail"),
  ("apiVersion: platform.wasp.silvios.me/v1alpha1\nkind: InitConfig\ntarget: azure\n", "target"),
  ("apiVersion: platform.wasp.silvios.me/v1alpha1\nkind: InitConfig\nwithCrossplane: yes please\n", "withCrossplane"),
  ("- a list\n", "mapping"),
])
def test_invalid_file_is_refused(tmp_path, text, error):
  with pytest.raises(SettingsError, match=error):
    from_file(write(tmp_path, text))


def test_missing_file_is_refused(tmp_path):
  with pytest.raises(SettingsError, match="not found"):
    from_file(tmp_path / "missing.yaml")
