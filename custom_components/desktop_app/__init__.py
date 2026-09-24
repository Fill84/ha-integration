"""The Desktop App integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components import webhook as webhook_component
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_DEVICE_ID,
    ATTR_DEVICE_NAME,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_APP_VERSION,
    ATTR_WEBHOOK_ID,
    DATA_API_VIEW_REGISTERED,
    DATA_LAST_SEEN,
    DATA_AVAILABILITY_STATE,
    DATA_UPDATE_INTERVALS,
    DATA_PENDING_UPDATES,
    DATA_REGISTERED_SENSORS,
    DATA_REGISTRATION_LOCK,
    DATA_LOADED_DEVICES,
    DATA_STORE,
    DOMAIN,
    PLATFORMS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .http_api import (
    DesktopAppDataView,
    DesktopAppPingView,
    DesktopAppPingViewWithSlash,
    DesktopAppRegistrationView,
)
from .webhook import handle_webhook

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Desktop App integration."""
    _LOGGER.info(
        "Desktop App integration loading (registration API: /api/desktop_app/registrations)"
    )

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_data = await store.async_load() or {}

    # We deliberately do NOT load config entries, devices, or deleted_ids from
    # storage anymore — HA's own config_entries registry is the source of
    # truth for which devices are registered. The custom store now only holds
    # `registered_sensors`, which is sensor metadata we need to recreate
    # entities across restarts.
    hass.data[DOMAIN] = {
        DATA_PENDING_UPDATES: {},
        DATA_STORE: store,
        DATA_API_VIEW_REGISTERED: False,
        DATA_REGISTERED_SENSORS: stored_data.get(DATA_REGISTERED_SENSORS, {}),
        DATA_LOADED_DEVICES: set(),
        # Phase 3: per-device last-seen timestamps for the availability sensor
        DATA_LAST_SEEN: {},
        DATA_AVAILABILITY_STATE: {},
        DATA_UPDATE_INTERVALS: {},
    }

    # Register API views directly. The "http" dependency in manifest.json
    # guarantees that hass.http is available at this point. Views MUST be
    # registered here (synchronously during setup) — registering later via
    # callbacks would fail because the aiohttp router is frozen after startup.
    hass.http.register_view(DesktopAppPingView())
    hass.http.register_view(DesktopAppPingViewWithSlash())
    hass.http.register_view(DesktopAppRegistrationView())
    hass.http.register_view(DesktopAppDataView())
    hass.data[DOMAIN][DATA_API_VIEW_REGISTERED] = True
    _LOGGER.info(
        "Registered Desktop App API at /api/desktop_app/registrations, "
        "/api/desktop_app/ping, /api/desktop_app/update"
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Desktop App from a config entry."""
    registration = entry.data

    # Hub entry — only purpose is to keep the integration loaded so the
    # API views stay registered.  No device/webhook/platform setup needed.
    if registration.get("is_hub"):
        _LOGGER.info("Desktop App hub entry loaded — API views active")
        return True

    device_id = registration[ATTR_DEVICE_ID]
    webhook_id = registration[ATTR_WEBHOOK_ID]

    # Register device in device registry
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device_id)},
        name=registration.get(ATTR_DEVICE_NAME, "Desktop App"),
        manufacturer=registration.get(ATTR_MANUFACTURER, "Unknown"),
        model=registration.get(ATTR_MODEL, "Desktop"),
        sw_version=registration.get(ATTR_APP_VERSION),
    )

    from .const import DATA_AVAILABILITY_TIMER
    runtime = hass.data[DOMAIN]
    webhook_registered = False
    timer_started = False
    platform_setup_started = False
    try:
        # A stale registration can remain after an interrupted reload.
        webhook_component.async_unregister(hass, webhook_id)
        webhook_component.async_register(
            hass,
            DOMAIN,
            f"Desktop App ({registration.get(ATTR_DEVICE_NAME, device_id)})",
            webhook_id,
            handle_webhook,
            allowed_methods=["POST"],
        )
        webhook_registered = True
        runtime[DATA_PENDING_UPDATES][webhook_id] = {}

        if DATA_AVAILABILITY_TIMER not in runtime:
            from .availability import start_availability_timer
            runtime[DATA_AVAILABILITY_TIMER] = start_availability_timer(hass)
            timer_started = True

        platform_setup_started = True
        result = await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        if result is False:
            raise RuntimeError("Desktop App platforms failed to set up")
    except (Exception, asyncio.CancelledError):
        if platform_setup_started:
            try:
                await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
            except Exception:
                _LOGGER.exception("Could not unload partially started Desktop App platforms")
        if webhook_registered:
            webhook_component.async_unregister(hass, webhook_id)
        runtime[DATA_PENDING_UPDATES].pop(webhook_id, None)
        runtime[DATA_LAST_SEEN].pop(device_id, None)
        runtime[DATA_AVAILABILITY_STATE].pop(device_id, None)
        runtime[DATA_UPDATE_INTERVALS].pop(device_id, None)
        if timer_started and not runtime[DATA_LOADED_DEVICES]:
            unsubscribe = runtime.pop(DATA_AVAILABILITY_TIMER, None)
            if unsubscribe is not None:
                unsubscribe()
        raise

    hass.data[DOMAIN][DATA_LOADED_DEVICES].add(entry.entry_id)

    _LOGGER.info("Desktop App entry set up for device: %s", device_id)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Desktop App config entry."""
    # Hub entry — nothing to tear down
    if entry.data.get("is_hub"):
        return True

    registration = entry.data
    webhook_id = registration.get(ATTR_WEBHOOK_ID)

    # Keep the handler alive if unloading a platform fails.
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    # Unregister webhook
    if webhook_id:
        webhook_component.async_unregister(hass, webhook_id)
        hass.data[DOMAIN][DATA_PENDING_UPDATES].pop(webhook_id, None)
    device_id = registration.get(ATTR_DEVICE_ID)
    hass.data[DOMAIN][DATA_LAST_SEEN].pop(device_id, None)
    hass.data[DOMAIN][DATA_AVAILABILITY_STATE].pop(device_id, None)
    hass.data[DOMAIN][DATA_UPDATE_INTERVALS].pop(device_id, None)
    hass.data[DOMAIN][DATA_LOADED_DEVICES].discard(entry.entry_id)

    # If this was the last entry being unloaded, stop the availability timer.
    from .const import DATA_AVAILABILITY_TIMER
    if not hass.data[DOMAIN][DATA_LOADED_DEVICES]:
        unsub = hass.data[DOMAIN].pop(DATA_AVAILABILITY_TIMER, None)
        if unsub is not None:
            unsub()

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove only this device's persisted sensor metadata."""
    if entry.data.get("is_hub") or DOMAIN not in hass.data:
        return
    async with hass.data[DOMAIN].setdefault(DATA_REGISTRATION_LOCK, asyncio.Lock()):
        device_id = entry.data.get(ATTR_DEVICE_ID)
        devices = hass.data[DOMAIN].get(DATA_REGISTERED_SENSORS, {})
        removed = {
            key: value for key, value in devices.items()
            if value.get(ATTR_DEVICE_ID) == device_id
        }
        for key in removed:
            devices.pop(key)
        if removed:
            try:
                await _async_save_store(hass)
            except Exception:
                devices.update(removed)
                _LOGGER.exception("Could not persist removal of device %s", device_id)
                raise


async def _async_save_store(hass: HomeAssistant) -> None:
    """Persist sensor metadata so entities survive HA restarts."""
    store: Store = hass.data[DOMAIN][DATA_STORE]
    await store.async_save(
        {
            DATA_REGISTERED_SENSORS: hass.data[DOMAIN].get(DATA_REGISTERED_SENSORS, {}),
        }
    )
