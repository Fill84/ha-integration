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
    DATA_PENDING_UPDATES,
    DATA_REGISTERED_SENSORS,
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

    # Register the webhook handler. Defensive: if a stale registration is
    # somehow already in HA's webhook table (e.g. setup ran twice during a
    # reload), unregister first — async_register raises otherwise.
    webhook_component.async_unregister(hass, webhook_id)
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

    # Unload platforms
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove a Desktop App config entry. Nothing to clean up beyond what HA
    handles itself — device registry, entity registry, and our webhook
    registration are all torn down by async_unload_entry / HA's removal flow.
    """
    return


async def _async_save_store(hass: HomeAssistant) -> None:
    """Persist sensor metadata so entities survive HA restarts."""
    store: Store = hass.data[DOMAIN][DATA_STORE]
    await store.async_save(
        {
            DATA_REGISTERED_SENSORS: hass.data[DOMAIN].get(DATA_REGISTERED_SENSORS, {}),
        }
    )
