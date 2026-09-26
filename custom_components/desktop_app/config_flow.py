"""Config flow for Desktop App integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    ATTR_DEVICE_ID,
    ATTR_DEVICE_NAME,
    ATTR_WEBHOOK_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class DesktopAppConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Desktop App."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a real desktop entry through HA's authenticated flow API."""
        if user_input is None:
            return self.async_show_form(step_id="user")

        device_id = user_input.get(ATTR_DEVICE_ID)
        device_name = user_input.get(ATTR_DEVICE_NAME)
        webhook_id = user_input.get(ATTR_WEBHOOK_ID)
        if not (
            isinstance(device_id, str)
            and 0 < len(device_id) <= 128
            and isinstance(device_name, str)
            and 0 < len(device_name.strip()) <= 128
            and isinstance(webhook_id, str)
            and len(webhook_id) == 64
            and all(character in "0123456789abcdef" for character in webhook_id)
        ):
            return self.async_abort(reason="register_from_desktop")

        registration = {
            key: value for key, value in user_input.items()
            if key in {
                ATTR_DEVICE_ID,
                ATTR_DEVICE_NAME,
                ATTR_WEBHOOK_ID,
                "manufacturer",
                "model",
                "os_name",
                "os_version",
                "app_version",
            }
            and value is not None
        }
        for value in registration.values():
            if not isinstance(value, str) or len(value) > 128 or any(
                ord(character) < 32 for character in value
            ):
                return self.async_abort(reason="register_from_desktop")

        # A previous attempt may have created the entry before the desktop
        # received its first webhook acknowledgement. Let the same admin flow
        # recover that webhook instead of creating a duplicate device.
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(ATTR_DEVICE_ID) == device_id:
                return self.async_abort(
                    reason="already_registered",
                    description_placeholders={
                        ATTR_WEBHOOK_ID: entry.data[ATTR_WEBHOOK_ID]
                    },
                )

        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=device_name, data=registration)

    async def async_step_registration(
        self, registration_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle registration from the desktop app."""
        device_id = registration_data[ATTR_DEVICE_ID]
        device_name = registration_data.get(ATTR_DEVICE_NAME, "Desktop App")

        # Set unique ID based on device_id to prevent duplicates
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(updates=registration_data)

        _LOGGER.info(
            "Creating config entry for device: %s (%s)",
            device_name,
            device_id,
        )

        return self.async_create_entry(
            title=device_name,
            data=registration_data,
        )
