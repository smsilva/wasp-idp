"""The settings of `platform init` (#462): from flags, the init file, the cluster (values an earlier
init remembered) or defaults, in that order, each with the place it came from."""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .. import config

API_VERSION = "platform.wasp.silvios.me/v1alpha1"
KIND = "InitConfig"
TARGETS = ("local",)
# Setting name, its key in the file and its default.
SETTINGS = (("target", "target", "local"), ("admins", "admins", []), ("aws_profile", "awsProfile", None), ("with_crossplane", "withCrossplane", False))
# Enough to catch a placeholder left in the command (`email_not_filled`), not a full RFC 5322 check.
# No comma nor quote: the cluster keeps the list comma-separated, and each one lands in a JSON claim.
EMAIL = re.compile(r'[^@\s,"]+@[^@\s,"]+\.[^@\s,"]+')


class SettingsError(Exception):
  pass


@dataclass(frozen=True)
class Setting:
  value: object
  source: str


def default_file() -> Path:
  return config.config_dir() / "init.yaml"


def check_admin(value: str) -> str:
  if not isinstance(value, str) or not EMAIL.fullmatch(value):
    raise SettingsError(f"'{value}' is not an e-mail")
  return value


def check_target(value: str) -> str:
  if value not in TARGETS:
    raise SettingsError(f"target '{value}' is not supported yet")
  return value


def from_file(path: Path) -> dict:
  """The settings of an init file, by setting name; a key it does not know is an error, so a typo never
  falls back to a default unnoticed."""
  if not path.is_file():
    raise SettingsError(f"{path} not found")
  try:
    document = yaml.safe_load(path.read_text())
  except yaml.YAMLError as error:
    raise SettingsError(f"{path} is not valid YAML: {error}") from None
  if not isinstance(document, dict):
    raise SettingsError(f"{path} must be a mapping")
  if document.pop("apiVersion", None) != API_VERSION:
    raise SettingsError(f"{path}: apiVersion must be {API_VERSION}")
  if document.pop("kind", None) != KIND:
    raise SettingsError(f"{path}: kind must be {KIND}")
  keys = {key: name for name, key, _ in SETTINGS}
  unknown = sorted(set(document) - set(keys))
  if unknown:
    raise SettingsError(f"{path}: unknown key(s) {', '.join(unknown)}; known: {', '.join(keys)}")
  values = {keys[key]: value for key, value in document.items()}
  try:
    if "target" in values:
      check_target(values["target"])
    admins = values.get("admins") or []
    if not isinstance(admins, list):
      raise SettingsError("admins must be a list of e-mails")
    for admin in admins:
      check_admin(admin)
  except SettingsError as error:
    raise SettingsError(f"{path}: {error}") from None
  if not isinstance(values.get("with_crossplane", False), bool):
    raise SettingsError(f"{path}: withCrossplane must be true or false")
  if not isinstance(values.get("aws_profile") or "", str):
    raise SettingsError(f"{path}: awsProfile must be a profile name")
  return values


def resolve(flags: dict, file: dict, file_source: str | None, remembered: dict) -> dict[str, Setting]:
  """flags: None (or an empty list) for a flag not given. remembered: what the cluster keeps from an
  earlier init. A list replaces the one below it whole: admins given by flag are the whole list."""
  settings = {}
  for name, _, default in SETTINGS:
    if flags.get(name) not in (None, []):
      settings[name] = Setting(flags[name], "flag")
    elif file.get(name) not in (None, []):
      settings[name] = Setting(file[name], file_source)
    elif remembered.get(name) not in (None, []):
      settings[name] = Setting(remembered[name], "cluster")
    else:
      settings[name] = Setting(default, "default")
  return settings


def to_file(settings: dict[str, Setting]) -> str:
  """The cloud settings (awsProfile, withCrossplane) enter the file only when set: unset, they are noise."""
  values = {key: settings[name].value for name, key, _ in SETTINGS}
  document = {"apiVersion": API_VERSION, "kind": KIND, **{key: value for key, value in values.items() if value not in (None, False)}}
  return yaml.safe_dump(document, sort_keys=False)
