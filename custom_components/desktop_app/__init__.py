"""The Desktop App integration."""

from __future__ import annotations

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
    DATA_CONFIG_ENTRIES,
    DATA_DEVICES,
    DATA_DELETED_IDS,
    DATA_PENDING_UPDATES,
    DATA_STORE,
    DOMAIN,
    PLATFORMS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .helpers import get_device_info
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

    hass.data[DOMAIN] = {
        DATA_CONFIG_ENTRIES: stored_data.get(DATA_CONFIG_ENTRIES, {}),
        DATA_DEVICES: stored_data.get(DATA_DEVICES, {}),
        DATA_DELETED_IDS: stored_data.get(DATA_DELETED_IDS, []),
        DATA_PENDING_UPDATES: {},
        DATA_STORE: store,
        DATA_API_VIEW_REGISTERED: False,
        "registered_sensors": stored_data.get("registered_sensors", {}),
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

    # Store config entry data
    hass.data[DOMAIN][DATA_CONFIG_ENTRIES][entry.entry_id] = dict(registration)

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

    # Register webhook handler
    webhook_component.async_register(
        hass,
        DOMAIN,
        f"Desktop App ({registration.get(ATTR_DEVICE_NAME, device_id)})",
        webhook_id,
        handle_webhook,
        allowed_methods=["POST"],
    )

    # Initialize pending updates dict for this entry
    hass.data[DOMAIN][DATA_PENDING_UPDATES][webhook_id] = {}

    # Forward setup to sensor and binary_sensor platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("Desktop App entry set up for device: %s", device_id)

    # Save store
    await _async_save_store(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Desktop App config entry."""
    # Hub entry — nothing to tear down
    if entry.data.get("is_hub"):
        return True

    registration = entry.data
    webhook_id = registration.get(ATTR_WEBHOOK_ID)

    # Unregister webhook
    if webhook_id:
        webhook_component.async_unregister(hass, webhook_id)
        hass.data[DOMAIN][DATA_PENDING_UPDATES].pop(webhook_id, None)

    # Remove config entry data
    hass.data[DOMAIN][DATA_CONFIG_ENTRIES].pop(entry.entry_id, None)

    # Unload platforms
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unloaded:
        await _async_save_store(hass)

    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a Desktop App config entry."""
    device_id = entry.data.get(ATTR_DEVICE_ID)
    if device_id:
        deleted_ids = hass.data[DOMAIN][DATA_DELETED_IDS]
        if device_id not in deleted_ids:
            deleted_ids.append(device_id)
        await _async_save_store(hass)


async def _async_save_store(hass: HomeAssistant) -> None:
    """Save data to store."""
    store: Store = hass.data[DOMAIN][DATA_STORE]
    await store.async_save(
        {
            DATA_CONFIG_ENTRIES: hass.data[DOMAIN][DATA_CONFIG_ENTRIES],
            DATA_DEVICES: hass.data[DOMAIN][DATA_DEVICES],
            DATA_DELETED_IDS: hass.data[DOMAIN][DATA_DELETED_IDS],
            "registered_sensors": hass.data[DOMAIN].get("registered_sensors", {}),
        }
    )
