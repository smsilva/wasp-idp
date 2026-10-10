import re
from datetime import datetime, timedelta, timezone

_DURATION = re.compile(r"^(\d+)([mhdw])$")
_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


def parse_duration(value: str) -> timedelta:
  """Parse a short duration such as 30m, 12h, 3d or 1w."""
  match = _DURATION.match(value.strip())
  if not match or int(match.group(1)) == 0:
    raise ValueError(f"invalid duration '{value}': use <n>m, <n>h, <n>d or <n>w")
  amount, unit = match.groups()
  return timedelta(**{_UNITS[unit]: int(amount)})


def expires_at(value: str, now: datetime | None = None) -> str:
  now = now or datetime.now(timezone.utc)
  return format_time(now + parse_duration(value))


def format_time(moment: datetime) -> str:
  return moment.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
