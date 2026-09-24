"""HTTP API for Desktop App device registration."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from aiohttp.web import Request, Response

from homeassistant.components import webhook as webhook_component
from homeassistant.core import HomeAssistant
from homeassistant.components.http import KEY_HASS_USER
from homeassistant.helpers.http import HomeAssistantView
from homeassistant.loader import async_get_integration

from .const import (
    ATTR_APP_VERSION,
    ATTR_DEVICE_ID,
    ATTR_DEVICE_NAME,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_OS_NAME,
    ATTR_OS_VERSION,
    ATTR_WEBHOOK_ID,
    DOMAIN,
    DATA_LOADED_DEVICES,
)
from .helpers import error_response, registration_response

_LOGGER = logging.getLogger(__name__)

REGISTRATION_SCHEMA_REQUIRED = [ATTR_DEVICE_ID, ATTR_DEVICE_NAME]
REGISTRATION_SCHEMA_OPTIONAL = [
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_OS_NAME,
    ATTR_OS_VERSION,
    ATTR_APP_VERSION,
]


def _valid_registration_text(value: Any, *, required: bool = False) -> bool:
    if value is None:
        return not required
    return (
        isinstance(value, str)
        and (not required or bool(value.strip()))
        and len(value) <= 128
        and not any(ord(char) < 32 for char in value)
    )


class DesktopAppPingView(HomeAssistantView):
    """Health check endpoint to verify the Desktop App integration is loaded and reachable."""

    url = "/api/desktop_app/ping"
    name = "api:desktop_app:ping"
    requires_auth = False

    async def get(self, request: Request) -> Response:
        """Return 200 so clients can verify the integration is reachable (e.g. before reverse proxy)."""
        return self.json_message("Desktop App integration is loaded")


class DesktopAppPingViewWithSlash(DesktopAppPingView):
    """Same as ping but for URL with trailing slash (e.g. curl .../ping/)."""

    url = "/api/desktop_app/ping/"
    name = "api:desktop_app:ping_slash"


def _ensure_webhook_registered(
    hass: HomeAssistant,
    webhook_id: str,
    device_name: str,
) -> None:
    """Idempotently (re)register the webhook handler.

    Covers the case where async_setup_entry registered the webhook on
    startup but it's no longer present in HA's webhook table (an exception
    during setup, a stale-state edge case, or a reload race). Without this,
    the desktop app would keep getting 404 on the webhook URL even though
    the config entry still exists — which used to require manual user
    intervention to recover from.
    """
    from .webhook import handle_webhook  # local to avoid circular import

    # async_unregister is silent if the webhook isn't registered, so we can
    # call it unconditionally before async_register (which raises on dup).
    webhook_component.async_unregister(hass, webhook_id)
    webhook_component.async_register(
        hass,
        DOMAIN,
        f"Desktop App ({device_name})",
        webhook_id,
        handle_webhook,
        allowed_methods=["POST"],
    )


class DesktopAppRegistrationView(HomeAssistantView):
    """Handle Desktop App device registrations."""

    url = "/api/desktop_app/registrations"
    name = "api:desktop_app:registrations"
    requires_auth = True

    async def get(self, request: Request) -> Response:
        """Report the running integration version to authenticated clients."""
        integration = await async_get_integration(request.app["hass"], DOMAIN)
        return self.json({
            "message": "Desktop App registration API; use POST with device_id and device_name",
            "integration_version": str(integration.version) if integration.version else None,
        })

    async def post(self, request: Request) -> Response:
        """Handle device registration."""
        hass: HomeAssistant = request.app["hass"]
        user = request[KEY_HASS_USER]

        try:
            data: dict[str, Any] = await request.json()
        except ValueError:
            return error_response("Invalid JSON", status=400)
        if not isinstance(data, dict):
            return error_response("Body must be a JSON object", status=400)

        # Validate required fields
        for field in REGISTRATION_SCHEMA_REQUIRED:
            if field not in data:
                return error_response(f"Missing required field: {field}", status=400)

        device_id = data[ATTR_DEVICE_ID]
        if not _valid_registration_text(device_id, required=True):
            return error_response("Invalid device_id", status=400)
        if not _valid_registration_text(data[ATTR_DEVICE_NAME], required=True):
            return error_response("Invalid device_name", status=400)
        for field in REGISTRATION_SCHEMA_OPTIONAL:
            if field in data and not _valid_registration_text(data[field]):
                return error_response(f"Invalid {field}", status=400)

        # If a config entry already exists for this device_id, repair its
        # webhook registration (idempotent) and return the same webhook_id.
        # This is the key fix for the "register page keeps reappearing"
        # symptom: previously we returned the stored webhook_id without
        # checking whether HA's webhook table actually knew about it.
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.data.get("is_hub"):
                continue
            if entry.data.get(ATTR_DEVICE_ID) != device_id:
                continue

            owner_id = entry.data.get("owner_user_id")
            # A legacy entry without an owner cannot prove which ordinary HA
            # user created it. Only an admin may bind that entry to an owner.
            if owner_id is None and not user.is_admin:
                return error_response("Legacy device requires administrator ownership migration", status=403)
            if owner_id is not None and owner_id != user.id and not user.is_admin:
                return error_response("Device is registered to another user", status=403)
            if entry.entry_id not in hass.data.get(DOMAIN, {}).get(DATA_LOADED_DEVICES, set()):
                return error_response("Device entry is not loaded yet", status=503)
            if owner_id is None:
                hass.config_entries.async_update_entry(entry, data={**entry.data, "owner_user_id": user.id})

            webhook_id = entry.data[ATTR_WEBHOOK_ID]
            device_name = entry.data.get(ATTR_DEVICE_NAME, "Desktop App")
            try:
                _ensure_webhook_registered(hass, webhook_id, device_name)
            except Exception:  # noqa: BLE001 - log + report, don't crash registration
                _LOGGER.exception(
                    "Failed to repair webhook for existing device %s",
                    device_id,
                )
                return error_response(
                    "Could not repair webhook registration", status=500
                )

            _LOGGER.info(
                "Device %s already registered; reused webhook after defensive re-register",
                device_id,
            )
            return registration_response(webhook_id)

        # Fresh registration: new webhook_id, new config entry.
        webhook_id = secrets.token_hex(32)
        registration = {
            ATTR_DEVICE_ID: device_id,
            ATTR_DEVICE_NAME: data[ATTR_DEVICE_NAME],
            ATTR_WEBHOOK_ID: webhook_id,
            "owner_user_id": user.id,
        }
        for field in REGISTRATION_SCHEMA_OPTIONAL:
            if field in data:
                registration[field] = data[field]

        _LOGGER.info("Registering new Desktop App device: %s", device_id)

        # Start config flow with registration source
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "registration"},
            data=registration,
        )

        if result.get("type") == "create_entry":
            _LOGGER.info("Device %s registered successfully", device_id)
            return registration_response(webhook_id)

        _LOGGER.error(
            "Failed to create config entry for device %s",
            device_id,
        )
        return error_response("Failed to register device", status=500)
