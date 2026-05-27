"""Unit tests for the Phase 3 availability layer.

These tests load `availability.py` as a standalone module (via
importlib.util.spec_from_file_location) so they don't drag in the
package-level __init__.py, which imports homeassistant.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone


_AVAIL_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "custom_components",
    "desktop_app",
    "availability.py",
)


def _load_availability_module():
    spec = importlib.util.spec_from_file_location("avail_standalone", _AVAIL_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Pre-stub the `.const` import so any lazy access inside the module body
    # (none in the pure path, but defensive) doesn't fail. Pure functions
    # don't need it.
    sys.modules.setdefault("avail_standalone", mod)
    spec.loader.exec_module(mod)
    return mod


avail = _load_availability_module()
is_device_online = avail.is_device_online
timeout_threshold = avail.timeout_threshold
DesktopAppAvailabilitySensor = avail.DesktopAppAvailabilitySensor


def test_is_device_online_true_within_window():
    now = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
    last_seen = now - timedelta(seconds=60)
    # update_interval=60 -> timeout at 150s. last_seen 60s ago -> online.
    assert is_device_online(last_seen=last_seen, now=now, update_interval=60) is True


def test_is_device_online_false_after_timeout():
    now = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
    last_seen = now - timedelta(seconds=200)
    # update_interval=60 -> timeout at 150s. last_seen 200s ago -> offline.
    assert is_device_online(last_seen=last_seen, now=now, update_interval=60) is False


def test_is_device_online_false_when_last_seen_missing():
    now = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
    assert is_device_online(last_seen=None, now=now, update_interval=60) is False


def test_timeout_threshold_default_factor():
    # update_interval=60 -> 60 * 2.5 = 150
    assert timeout_threshold(update_interval=60) == 150.0


def test_timeout_threshold_minimum_floor():
    # Very small update intervals should still allow at least ~10 seconds of
    # tolerance -- otherwise a momentary blip flips the entity offline.
    assert timeout_threshold(update_interval=1) >= 10.0


def test_availability_sensor_initial_state_is_unavailable_until_first_seen():
    # Until the first heartbeat arrives, is_on must be False and the
    # entity must NOT be reported as 'unavailable' (we want a definite
    # "offline" reading, not nothing).
    sensor = DesktopAppAvailabilitySensor(
        device_id="dev-1",
        device_name="Test PC",
        update_interval=60,
    )
    assert sensor.is_on is False
    assert sensor.available is True
    assert sensor.device_class == "connectivity"


def test_availability_sensor_handle_signal_sets_state():
    sensor = DesktopAppAvailabilitySensor(
        device_id="dev-1",
        device_name="Test PC",
        update_interval=60,
    )
    sensor._handle_update(True)
    assert sensor.is_on is True
    sensor._handle_update(False)
    assert sensor.is_on is False
