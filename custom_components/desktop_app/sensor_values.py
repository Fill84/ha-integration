"""Small, Home Assistant independent value conversions."""

from datetime import datetime
from typing import Any


def timestamp_value(value: Any) -> datetime | None:
    """HA timestamp sensors require an aware datetime, never a display string."""
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    except ValueError:
        return None
    if isinstance(parsed, datetime) and parsed.tzinfo and parsed.utcoffset() is not None:
        return parsed
    return None
