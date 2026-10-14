import os
from pathlib import Path

import yaml


def config_dir() -> Path:
  base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
  return Path(base) / "platform"


def state_dir() -> Path:
  """Run records (the logs of `platform init`, #458): XDG_STATE_HOME, so tests isolate it like the config."""
  base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
  return Path(base) / "platform"


def config_path() -> Path:
  return config_dir() / "config.yaml"


def load() -> dict:
  path = config_path()
  if not path.exists():
    return {}
  return yaml.safe_load(path.read_text()) or {}


def save(values: dict) -> Path:
  path = config_path()
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(yaml.safe_dump(values, sort_keys=False))
  return path


def api_url() -> str | None:
  return os.environ.get("PLATFORM_API_URL") or load().get("api_url")
