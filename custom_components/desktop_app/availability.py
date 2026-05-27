"""Availability tracking for the Desktop App integration.

Pure-function helpers (no HA imports at module top) live at the top so they
can be unit tested without a HomeAssistant install. The
DesktopAppAvailabilitySensor entity class and the periodic timer wiring sit
below, with their HA imports inside the class/function bodies.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

# Constants are duplicated here (not imported from .const) so this module's
# pure functions can be unit-tested without instantiating the package, which
# would trigger HomeAssistant imports in __init__.py.
AVAILABILITY_TIMEOUT_FACTOR = 2.5
AVAILABILITY_CHECK_INTERVAL_SECONDS = 30

# Minimum time a device may be silent before we consider it offline. Prevents
# tiny update intervals from causing flapping on a single packet loss.
_MIN_TIMEOUT_SECONDS = 10.0


def timeout_threshold(update_interval: int | float) -> float:
    """How many seconds of silence count as offline."""
    return max(_MIN_TIMEOUT_SECONDS, float(update_interval) * AVAILABILITY_TIMEOUT_FACTOR)


def is_device_online(
    *,
    last_seen: datetime | None,
    now: datetime,
    update_interval: int | float,
) -> bool:
    """Decide whether a device is currently considered online.

    Returns False when last_seen is None (never seen).
    """
    if last_seen is None:
        return False
    age_seconds = (now - last_seen).total_seconds()
    return age_seconds <= timeout_threshold(update_interval)


def evaluate_devices(
    *,
    last_seen: dict[str, datetime],
    update_intervals: dict[str, int | float],
    current_state: dict[str, bool],
    now: datetime,
) -> dict[str, bool]:
    """Return the subset of devices whose availability should flip.

    Stateless: caller is responsible for storing `current_state` between calls.
    """
    flips: dict[str, bool] = {}
    for device_id, ts in last_seen.items():
        interval = update_intervals.get(device_id, 60)
        new_state = is_device_online(last_seen=ts, now=now, update_interval=interval)
        if current_state.get(device_id) != new_state:
            flips[device_id] = new_state
    return flips


def offline_signal_payload() -> bool:
    """Constant returned to the dispatcher when a device sends device_offline.

    Exists as a function so the constant is testable without importing the
    webhook module's HA-side imports.
    """
    return False


# --- Entity class and timer wiring (HA imports done lazily inside) ---


class DesktopAppAvailabilitySensor:
    """A binary_sensor that reflects whether a device's desktop app is
    currently sending heartbeats. Always available (never 'unavailable')
    so HA can render a clear 'offline' state.

    Subclasses BinarySensorEntity at runtime (we resolve the base class
    inside the metaclass-free __init_subclass__ pattern below) so this
    module is importable without homeassistant installed.
    """

    # Class body intentionally minimal at import time. The actual entity
    # is built by `_AvailabilitySensorImpl` below which inherits from
    # BinarySensorEntity. The pure-Python class above exists only for tests
    # that want to assert on attribute values without needing an HA install.

    def __init__(
        self,
        *,
        device_id: str,
        device_name: str,
        update_interval: int | float,
    ) -> None:
        self._device_id = device_id
        self._device_name = device_name
        self._update_interval = update_interval
        self._attr_unique_id = f"{device_id}_online"
        self._attr_is_on = False

    @property
    def is_on(self) -> bool:
        return bool(self._attr_is_on)

    @property
    def available(self) -> bool:
        # Never unavailable -- offline is itself a real state.
        return True

    @property
    def device_class(self) -> str:
        return "connectivity"

    def _handle_update(self, is_online: Any) -> None:
        self._attr_is_on = bool(is_online)


def build_ha_availability_sensor(
    *,
    device_id: str,
    device_name: str,
    update_interval: int | float,
):
    """Construct the actual HA-aware entity. Imports homeassistant lazily
    so this module remains importable in unit tests without HA installed.
    """
    from homeassistant.components.binary_sensor import (
        BinarySensorDeviceClass,
        BinarySensorEntity,
    )
    from homeassistant.core import callback
    from homeassistant.helpers.dispatcher import async_dispatcher_connect

    class _AvailabilitySensorImpl(BinarySensorEntity):
        _attr_should_poll = False
        _attr_has_entity_name = True
        _attr_name = "Online"
        _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        _attr_icon = "mdi:wifi-check"

        def __init__(self, dev_id: str, dev_name: str, interval: int | float) -> None:
            self._device_id = dev_id
            self._device_name = dev_name
            self._update_interval = interval
            self._attr_unique_id = f"{dev_id}_online"
            self._attr_is_on = False

        @property
        def device_info(self):
            from .const import DOMAIN
            return {"identifiers": {(DOMAIN, self._device_id)}}

        async def async_added_to_hass(self) -> None:
            from .const import SIGNAL_AVAILABILITY_UPDATE
            await super().async_added_to_hass()
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_AVAILABILITY_UPDATE.format(self._device_id),
                    self._handle_update,
                )
            )

        @callback
        def _handle_update(self, is_online: bool) -> None:
            self._attr_is_on = bool(is_online)
            if self.hass is not None:
                self.async_write_ha_state()

    return _AvailabilitySensorImpl(device_id, device_name, update_interval)


def start_availability_timer(hass) -> Callable[[], None]:
    """Schedule a periodic availability check. Returns the unsubscribe.

    Stored on hass.data so the integration can cancel it during unload.
    """
    from datetime import timedelta
    from homeassistant.core import callback as ha_callback
    from homeassistant.helpers.dispatcher import async_dispatcher_send
    from homeassistant.helpers.event import async_track_time_interval
    from homeassistant.util import dt as dt_util

    from .const import DATA_LAST_SEEN, DOMAIN, SIGNAL_AVAILABILITY_UPDATE

    current_state: dict[str, bool] = {}

    @ha_callback
    def _tick(_now):
        last_seen = hass.data[DOMAIN].get(DATA_LAST_SEEN, {})
        intervals = {
            entry.data.get("device_id"): entry.data.get("update_interval", 60)
            for entry in hass.config_entries.async_entries(DOMAIN)
        }
        flips = evaluate_devices(
            last_seen=last_seen,
            update_intervals=intervals,
            current_state=current_state,
            now=dt_util.utcnow(),
        )
        for device_id, is_online in flips.items():
            current_state[device_id] = is_online
            async_dispatcher_send(
                hass,
                SIGNAL_AVAILABILITY_UPDATE.format(device_id),
                is_online,
            )

    return async_track_time_interval(
        hass,
        _tick,
        timedelta(seconds=AVAILABILITY_CHECK_INTERVAL_SECONDS),
    )
