"""Timestamp normalization expected by Home Assistant's sensor contract."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path


source = Path(__file__).resolve().parents[1] / "custom_components/desktop_app/sensor_values.py"
spec = importlib.util.spec_from_file_location("sensor_values_standalone", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_timestamp_requires_timezone_and_rejects_display_value():
    value = module.timestamp_value("2026-05-26T12:00:00+00:00")
    assert value == datetime(2026, 5, 26, 12, tzinfo=timezone.utc)
    assert module.timestamp_value("2026-05-26 12:00 UTC") is None
    assert module.timestamp_value("2026-05-26T12:00:00") is None
    assert module.timestamp_value(None) is None
