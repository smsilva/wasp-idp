from datetime import datetime, timezone

import pytest

from platform_api.durations import expires_at, parse_duration


@pytest.mark.parametrize("value,seconds", [("30m", 1800), ("12h", 43200), ("3d", 259200), ("1w", 604800)])
def test_parse_duration(value, seconds):
  assert parse_duration(value).total_seconds() == seconds


@pytest.mark.parametrize("value", ["", "3", "d", "0h", "-1d", "3 days", "1y"])
def test_parse_duration_rejects(value):
  with pytest.raises(ValueError):
    parse_duration(value)


def test_expires_at():
  now = datetime(2026, 10, 10, 12, 0, 30, 123456, tzinfo=timezone.utc)
  assert expires_at("3d", now) == "2026-10-13T12:00:30Z"
