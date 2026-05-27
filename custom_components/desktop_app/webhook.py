"""Webhook handlers for the Desktop App integration."""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

from aiohttp.web import Request, Response

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ATTR_DEVICE_ID,
    ATTR_SENSOR_ATTRIBUTES,
    ATTR_SENSOR_DEVICE_CLASS,
    ATTR_SENSOR_ENTITY_CATEGORY,
    ATTR_SENSOR_ICON,
    ATTR_SENSOR_NAME,
    ATTR_SENSOR_STATE,
    ATTR_SENSOR_STATE_CLASS,
    ATTR_SENSOR_TYPE,
    ATTR_SENSOR_UNIQUE_ID,
    ATTR_SENSOR_UNIT_OF_MEASUREMENT,
    ATTR_WEBHOOK_ID,
    COMMAND_DEVICE_OFFLINE,
    COMMAND_REGISTER_SENSOR,
    COMMAND_UPDATE_REGISTRATION,
    COMMAND_UPDATE_SENSOR_STATES,
    DATA_PENDING_UPDATES,
    DATA_REGISTERED_SENSORS,
    DOMAIN,
    SIGNAL_SENSOR_REGISTER,
    SIGNAL_SENSOR_UPDATE,
)
from .helpers import error_response, webhook_response

_LOGGER = logging.getLogger(__name__)

# Registry of webhook command handlers
WEBHOOK_COMMANDS: dict[
    str,
    Callable[[HomeAssistant, ConfigEntry, str, dict], Coroutine[Any, Any, Response]],
] = {}


def webhook_command(command_type: str):
    """Decorator to register a webhook command handler."""

    def decorator(func):
        WEBHOOK_COMMANDS[command_type] = func
        return func

    return decorator


def _find_entry_by_webhook(hass: HomeAssistant, webhook_id: str) -> ConfigEntry | None:
    """Return the config entry for the given webhook_id, or None.

    HA's own config_entries registry is the source of truth — we no longer
    keep a parallel store, so there is nothing to drift out of sync with.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(ATTR_WEBHOOK_ID) == webhook_id:
            return entry
    return None


async def handle_webhook(
    hass: HomeAssistant, webhook_id: str, request: Request
) -> Response:
    """Handle incoming webhook requests from the Desktop App."""
    try:
        data: dict[str, Any] = await request.json()
    except ValueError:
        return error_response("Invalid JSON", status=400)

    command_type = data.get("type")
    if not command_type:
        return error_response("Missing 'type' field", status=400)

    handler = WEBHOOK_COMMANDS.get(command_type)
    if handler is None:
        _LOGGER.warning("Unknown webhook command type: %s", command_type)
        return error_response(f"Unknown command type: {command_type}", status=400)

    entry = _find_entry_by_webhook(hass, webhook_id)
    if entry is None:
        return error_response("Device not registered", status=410)

    _LOGGER.debug(
        "Handling webhook command '%s' for device %s",
        command_type,
        entry.data.get(ATTR_DEVICE_ID, "unknown"),
    )

    # Phase 3: every command except device_offline counts as a heartbeat.
    # device_offline is the graceful "I'm going down" signal — recording it
    # as activity would defeat its purpose (the periodic timer would then
    # flip the device back online on its next tick).
    if command_type != COMMAND_DEVICE_OFFLINE:
        from homeassistant.util import dt as dt_util
        from .const import DATA_LAST_SEEN, SIGNAL_AVAILABILITY_UPDATE
        device_id = entry.data[ATTR_DEVICE_ID]
        hass.data[DOMAIN].setdefault(DATA_LAST_SEEN, {})[device_id] = dt_util.utcnow()
        async_dispatcher_send(
            hass,
            SIGNAL_AVAILABILITY_UPDATE.format(device_id),
            True,
        )

    return await handler(hass, entry, webhook_id, data.get("data", {}))


@webhook_command(COMMAND_REGISTER_SENSOR)
async def handle_register_sensor(
    hass: HomeAssistant,
    entry: ConfigEntry,
    webhook_id: str,
    data: dict[str, Any],
) -> Response:
    """Register a new sensor entity."""
    required_fields = [ATTR_SENSOR_UNIQUE_ID, ATTR_SENSOR_NAME, ATTR_SENSOR_TYPE]
    for field in required_fields:
        if field not in data:
            return error_response(f"Missing required field: {field}", status=400)

    sensor_type = data[ATTR_SENSOR_TYPE]
    if sensor_type not in ("sensor", "binary_sensor"):
        return error_response(
            f"Invalid sensor type: {sensor_type}. Must be 'sensor' or 'binary_sensor'.",
            status=400,
        )

    device_id = entry.data[ATTR_DEVICE_ID]
    sensor_unique_id = data[ATTR_SENSOR_UNIQUE_ID]
    unique_store_key = f"{device_id}_{sensor_unique_id}"

    devices = hass.data[DOMAIN].setdefault(DATA_REGISTERED_SENSORS, {})
    is_reregistration = unique_store_key in devices

    sensor_data = {
        ATTR_SENSOR_UNIQUE_ID: sensor_unique_id,
        ATTR_SENSOR_NAME: data[ATTR_SENSOR_NAME],
        ATTR_SENSOR_TYPE: sensor_type,
        ATTR_SENSOR_STATE: data.get(ATTR_SENSOR_STATE),
        ATTR_SENSOR_ICON: data.get(ATTR_SENSOR_ICON),
        ATTR_SENSOR_DEVICE_CLASS: data.get(ATTR_SENSOR_DEVICE_CLASS),
        ATTR_SENSOR_UNIT_OF_MEASUREMENT: data.get(ATTR_SENSOR_UNIT_OF_MEASUREMENT),
        ATTR_SENSOR_STATE_CLASS: data.get(ATTR_SENSOR_STATE_CLASS),
        ATTR_SENSOR_ENTITY_CATEGORY: data.get(ATTR_SENSOR_ENTITY_CATEGORY),
        ATTR_SENSOR_ATTRIBUTES: data.get(ATTR_SENSOR_ATTRIBUTES, {}),
        "unique_store_key": unique_store_key,
        ATTR_DEVICE_ID: device_id,
    }

    # Store sensor registration (overwrites any prior entry)
    devices[unique_store_key] = sensor_data

    # Persist to store so sensors survive HA restarts
    from . import _async_save_store
    await _async_save_store(hass)

    # Dispatch signal for dynamic entity creation. If an entity for this
    # unique_id already exists, sensor.py will skip creation — we then push
    # the new metadata directly to the existing entity via SIGNAL_SENSOR_UPDATE
    # so its device_class/unit/state_class can change at runtime (e.g. when
    # the desktop app switches a sensor's state shape between versions).
    register_signal = SIGNAL_SENSOR_REGISTER.format(device_id, sensor_type)
    async_dispatcher_send(hass, register_signal, sensor_data)

    if is_reregistration:
        update_signal = SIGNAL_SENSOR_UPDATE.format(device_id, sensor_unique_id)
        async_dispatcher_send(
            hass,
            update_signal,
            {
                ATTR_SENSOR_STATE: data.get(ATTR_SENSOR_STATE),
                ATTR_SENSOR_ICON: data.get(ATTR_SENSOR_ICON),
                ATTR_SENSOR_ATTRIBUTES: data.get(ATTR_SENSOR_ATTRIBUTES, {}),
                ATTR_SENSOR_DEVICE_CLASS: data.get(ATTR_SENSOR_DEVICE_CLASS),
                ATTR_SENSOR_UNIT_OF_MEASUREMENT: data.get(
                    ATTR_SENSOR_UNIT_OF_MEASUREMENT
                ),
                ATTR_SENSOR_STATE_CLASS: data.get(ATTR_SENSOR_STATE_CLASS),
            },
        )

    _LOGGER.info(
        "%s sensor '%s' (%s) for device %s",
        "Re-registered" if is_reregistration else "Registered",
        data[ATTR_SENSOR_NAME],
        sensor_type,
        device_id,
    )

    return webhook_response({"success": True})


@webhook_command(COMMAND_UPDATE_SENSOR_STATES)
async def handle_update_sensor_states(
    hass: HomeAssistant,
    entry: ConfigEntry,
    webhook_id: str,
    data: dict[str, Any],
) -> Response:
    """Handle batch sensor state updates."""
    sensor_states = data.get("sensors", [])
    if not isinstance(sensor_states, list):
        return error_response("'sensors' must be a list", status=400)

    device_id = entry.data[ATTR_DEVICE_ID]
    pending = hass.data[DOMAIN][DATA_PENDING_UPDATES].setdefault(webhook_id, {})

    for sensor_update in sensor_states:
        sensor_unique_id = sensor_update.get(ATTR_SENSOR_UNIQUE_ID)
        if not sensor_unique_id:
            continue

        unique_store_key = f"{device_id}_{sensor_unique_id}"

        update_data = {
            ATTR_SENSOR_STATE: sensor_update.get(ATTR_SENSOR_STATE),
            ATTR_SENSOR_ICON: sensor_update.get(ATTR_SENSOR_ICON),
            ATTR_SENSOR_ATTRIBUTES: sensor_update.get(ATTR_SENSOR_ATTRIBUTES, {}),
        }

        # Buffer in pending updates
        pending[unique_store_key] = update_data

        # Dispatch signal to individual entity
        signal = SIGNAL_SENSOR_UPDATE.format(device_id, sensor_unique_id)
        async_dispatcher_send(hass, signal, update_data)

    _LOGGER.debug(
        "Updated %d sensor states for device %s",
        len(sensor_states),
        device_id,
    )

    return webhook_response({"success": True})


@webhook_command(COMMAND_UPDATE_REGISTRATION)
async def handle_update_registration(
    hass: HomeAssistant,
    entry: ConfigEntry,
    webhook_id: str,
    data: dict[str, Any],
) -> Response:
    """Update device registration info (os_version, app_version, device_name).

    Persists through HA's own config_entries API so the change survives
    restarts and is visible to anyone using `entry.data`.
    """
    device_id = entry.data[ATTR_DEVICE_ID]

    updatable_fields = ("os_version", "app_version", "device_name")
    updates = {k: data[k] for k in updatable_fields if k in data}
    if not updates:
        return webhook_response({"success": True})

    new_data = {**entry.data, **updates}
    hass.config_entries.async_update_entry(entry, data=new_data)

    _LOGGER.info("Updated registration for device %s: %s", device_id, list(updates))

    return webhook_response({"success": True})


@webhook_command(COMMAND_DEVICE_OFFLINE)
async def handle_device_offline(
    hass: HomeAssistant,
    entry: ConfigEntry,
    webhook_id: str,
    data: dict[str, Any],
) -> Response:
    """Mark this device offline immediately (graceful shutdown signal)."""
    from .availability import offline_signal_payload
    from .const import SIGNAL_AVAILABILITY_UPDATE

    device_id = entry.data[ATTR_DEVICE_ID]
    async_dispatcher_send(
        hass,
        SIGNAL_AVAILABILITY_UPDATE.format(device_id),
        offline_signal_payload(),
    )
    _LOGGER.info("Device %s flagged offline by graceful shutdown signal", device_id)
    return webhook_response({"success": True})
