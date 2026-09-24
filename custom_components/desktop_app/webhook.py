"""Webhook handlers for the Desktop App integration."""

from __future__ import annotations

import logging
import math
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
    ATTR_SENSOR_UPDATE_AT_INTERVAL,
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
MAX_SENSORS_PER_DEVICE = 512


def _valid_text(value: Any, *, required: bool = False, limit: int = 128) -> bool:
    """Validate metadata without changing existing sensor identifiers."""
    if value is None:
        return not required
    return (
        isinstance(value, str)
        and (not required or bool(value.strip()))
        and len(value) <= limit
        and not any(ord(char) < 32 for char in value)
    )


def _valid_sensor_update(sensor: Any) -> bool:
    return (
        isinstance(sensor, dict)
        and _valid_text(sensor.get(ATTR_SENSOR_UNIQUE_ID), required=True)
        and isinstance(sensor.get(ATTR_SENSOR_ATTRIBUTES, {}), dict)
        and _valid_text(sensor.get(ATTR_SENSOR_ICON))
        and _valid_state(sensor.get(ATTR_SENSOR_STATE))
    )


def _valid_state(value: Any) -> bool:
    """HA entity states are scalar; nonfinite numbers cannot be represented."""
    return value is None or isinstance(value, (str, bool, int)) or (
        isinstance(value, float) and math.isfinite(value)
    )

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
    if not isinstance(data, dict):
        return error_response("Payload must be a JSON object", status=400)
    # Legacy desktop clients do not send a version. Reject unknown versions
    # before dispatch so a future wire format cannot silently mutate state.
    if data.get("protocol_version", 1) != 1 or isinstance(data.get("protocol_version", 1), bool):
        return error_response("Unsupported protocol version", status=400)

    command_type = data.get("type")
    if not _valid_text(command_type, required=True, limit=64):
        return error_response("Invalid 'type' field", status=400)

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

    payload = data.get("data", {})
    if not isinstance(payload, dict):
        return error_response("Command data must be a JSON object", status=400)

    response = await handler(hass, entry, webhook_id, payload)
    # Invalid commands and failed handlers must never revive a device.
    if command_type != COMMAND_DEVICE_OFFLINE and 200 <= response.status < 300:
        from homeassistant.util import dt as dt_util
        from .const import DATA_AVAILABILITY_STATE, DATA_LAST_SEEN, SIGNAL_AVAILABILITY_UPDATE
        device_id = entry.data[ATTR_DEVICE_ID]
        hass.data[DOMAIN].setdefault(DATA_LAST_SEEN, {})[device_id] = dt_util.utcnow()
        hass.data[DOMAIN].setdefault(DATA_AVAILABILITY_STATE, {})[device_id] = True
        async_dispatcher_send(
            hass,
            SIGNAL_AVAILABILITY_UPDATE.format(device_id),
            True,
        )

    return response


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
    if not _valid_text(data[ATTR_SENSOR_UNIQUE_ID], required=True):
        return error_response("Invalid sensor_unique_id", status=400)
    if not _valid_text(data[ATTR_SENSOR_NAME], required=True):
        return error_response("Invalid sensor_name", status=400)
    for field in (
        ATTR_SENSOR_ICON,
        ATTR_SENSOR_DEVICE_CLASS,
        ATTR_SENSOR_UNIT_OF_MEASUREMENT,
        ATTR_SENSOR_STATE_CLASS,
        ATTR_SENSOR_ENTITY_CATEGORY,
    ):
        if not _valid_text(data.get(field)):
            return error_response(f"Invalid {field}", status=400)
    if not isinstance(data.get(ATTR_SENSOR_ATTRIBUTES, {}), dict):
        return error_response("sensor_attributes must be an object", status=400)
    if not _valid_state(data.get(ATTR_SENSOR_STATE)):
        return error_response("sensor_state must be scalar", status=400)
    if not isinstance(data.get(ATTR_SENSOR_UPDATE_AT_INTERVAL, False), bool):
        return error_response("update_at_interval must be a boolean", status=400)

    device_id = entry.data[ATTR_DEVICE_ID]
    sensor_unique_id = data[ATTR_SENSOR_UNIQUE_ID]
    unique_store_key = f"{device_id}_{sensor_unique_id}"

    devices = hass.data[DOMAIN].setdefault(DATA_REGISTERED_SENSORS, {})
    is_reregistration = unique_store_key in devices
    if not is_reregistration and sum(
        sensor.get(ATTR_DEVICE_ID) == device_id for sensor in devices.values()
    ) >= MAX_SENSORS_PER_DEVICE:
        return error_response("Device sensor limit reached", status=400)

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
        ATTR_SENSOR_UPDATE_AT_INTERVAL: data.get(ATTR_SENSOR_UPDATE_AT_INTERVAL, False),
        "unique_store_key": unique_store_key,
        ATTR_DEVICE_ID: device_id,
    }

    previous = devices.get(unique_store_key)
    if previous is not None and previous.get(ATTR_SENSOR_TYPE) != sensor_type:
        return error_response("Changing an existing sensor's entity type is not supported", status=409)
    descriptor_keys = (
        ATTR_SENSOR_UNIQUE_ID, ATTR_SENSOR_NAME, ATTR_SENSOR_TYPE,
        ATTR_SENSOR_ICON, ATTR_SENSOR_DEVICE_CLASS,
        ATTR_SENSOR_UNIT_OF_MEASUREMENT, ATTR_SENSOR_STATE_CLASS,
        ATTR_SENSOR_ENTITY_CATEGORY,
        ATTR_SENSOR_UPDATE_AT_INTERVAL,
    )
    if previous is not None and all(previous.get(key) == sensor_data.get(key) for key in descriptor_keys):
        current_value = {
            ATTR_SENSOR_STATE: data.get(ATTR_SENSOR_STATE),
            ATTR_SENSOR_ATTRIBUTES: data.get(ATTR_SENSOR_ATTRIBUTES, {}),
        }
        hass.data[DOMAIN][DATA_PENDING_UPDATES].setdefault(webhook_id, {})[unique_store_key] = current_value
        async_dispatcher_send(
            hass,
            SIGNAL_SENSOR_UPDATE.format(device_id, sensor_unique_id),
            current_value,
        )
        return webhook_response({"success": True})

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
        update_data = {
            ATTR_SENSOR_NAME: data[ATTR_SENSOR_NAME],
            ATTR_SENSOR_STATE: data.get(ATTR_SENSOR_STATE),
            ATTR_SENSOR_ICON: data.get(ATTR_SENSOR_ICON),
            ATTR_SENSOR_ATTRIBUTES: data.get(ATTR_SENSOR_ATTRIBUTES, {}),
            ATTR_SENSOR_DEVICE_CLASS: data.get(ATTR_SENSOR_DEVICE_CLASS),
            ATTR_SENSOR_ENTITY_CATEGORY: data.get(ATTR_SENSOR_ENTITY_CATEGORY),
            ATTR_SENSOR_UNIT_OF_MEASUREMENT: data.get(ATTR_SENSOR_UNIT_OF_MEASUREMENT),
            ATTR_SENSOR_STATE_CLASS: data.get(ATTR_SENSOR_STATE_CLASS),
        }
        hass.data[DOMAIN][DATA_PENDING_UPDATES].setdefault(webhook_id, {})[unique_store_key] = update_data
        async_dispatcher_send(
            hass,
            update_signal,
            update_data,
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
    if any(not _valid_sensor_update(sensor) for sensor in sensor_states):
        return error_response("Invalid sensor update", status=400)
    if len(sensor_states) > MAX_SENSORS_PER_DEVICE:
        return error_response("Too many sensor updates", status=400)
    device_id = entry.data[ATTR_DEVICE_ID]
    registered = hass.data[DOMAIN].get(DATA_REGISTERED_SENSORS, {})
    received_ids = [sensor[ATTR_SENSOR_UNIQUE_ID] for sensor in sensor_states]
    if len(received_ids) != len(set(received_ids)):
        return error_response("Duplicate sensor update", status=400)
    if any(f"{device_id}_{sensor_id}" not in registered for sensor_id in received_ids):
        return error_response("Sensor is not registered", status=409)
    snapshot_scope = data.get("snapshot_scope")
    if snapshot_scope not in (None, "all", "dynamic"):
        return error_response("snapshot_scope must be 'all' or 'dynamic'", status=400)
    update_interval = data.get("update_interval")
    if update_interval is not None:
        if type(update_interval) is not int or not 5 <= update_interval <= 3600:
            return error_response("update_interval must be 5..3600 seconds", status=400)
        from .const import DATA_UPDATE_INTERVALS
        hass.data[DOMAIN].setdefault(DATA_UPDATE_INTERVALS, {})[entry.data[ATTR_DEVICE_ID]] = update_interval

    pending = hass.data[DOMAIN][DATA_PENDING_UPDATES].setdefault(webhook_id, {})
    received_ids = set(received_ids)

    for sensor_update in sensor_states:
        sensor_unique_id = sensor_update.get(ATTR_SENSOR_UNIQUE_ID)
        if not sensor_unique_id:
            continue

        unique_store_key = f"{device_id}_{sensor_unique_id}"

        update_data = {ATTR_SENSOR_STATE: sensor_update.get(ATTR_SENSOR_STATE)}
        for field in (ATTR_SENSOR_ICON, ATTR_SENSOR_ATTRIBUTES):
            if field in sensor_update:
                update_data[field] = sensor_update[field]

        # Buffer in pending updates
        pending[unique_store_key] = update_data

        # Dispatch signal to individual entity
        signal = SIGNAL_SENSOR_UPDATE.format(device_id, sensor_unique_id)
        async_dispatcher_send(hass, signal, update_data)

    # Older clients omit snapshot_scope and retain their previous behavior.
    # A complete snapshot explicitly clears missing readings while retaining
    # their registered unique IDs and existing HA automations.
    if snapshot_scope is not None:
        for sensor_data in list(registered.values()):
            if sensor_data.get(ATTR_DEVICE_ID) != device_id:
                continue
            sensor_unique_id = sensor_data[ATTR_SENSOR_UNIQUE_ID]
            if sensor_unique_id in received_ids:
                continue
            if snapshot_scope == "dynamic" and not sensor_data.get(ATTR_SENSOR_UPDATE_AT_INTERVAL, False):
                continue
            unique_store_key = f"{device_id}_{sensor_unique_id}"
            missing = {ATTR_SENSOR_STATE: None, ATTR_SENSOR_ATTRIBUTES: {}}
            pending[unique_store_key] = missing
            async_dispatcher_send(
                hass, SIGNAL_SENSOR_UPDATE.format(device_id, sensor_unique_id), missing
            )

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
    for field, value in updates.items():
        if not _valid_text(value, required=field == "device_name"):
            return error_response(f"Invalid {field}", status=400)
    if not updates:
        return webhook_response({"success": True})

    new_data = {**entry.data, **updates}
    hass.config_entries.async_update_entry(entry, data=new_data)
    from homeassistant.helpers import device_registry as dr
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device_id)},
        name=new_data.get("device_name", "Desktop App"),
        sw_version=new_data.get("app_version"),
    )

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
    from .const import DATA_AVAILABILITY_STATE, DATA_LAST_SEEN
    hass.data[DOMAIN].setdefault(DATA_AVAILABILITY_STATE, {})[device_id] = False
    hass.data[DOMAIN].setdefault(DATA_LAST_SEEN, {}).pop(device_id, None)
    async_dispatcher_send(
        hass,
        SIGNAL_AVAILABILITY_UPDATE.format(device_id),
        offline_signal_payload(),
    )
    _LOGGER.info("Device %s flagged offline by graceful shutdown signal", device_id)
    return webhook_response({"success": True})
