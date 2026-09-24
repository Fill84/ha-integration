# Desktop–Home Assistant protocol (version 1)

The desktop and this integration use a small JSON protocol. Configure a Home Assistant *Long-Lived Access Token* in the desktop app over a trusted HA URL. Never put a token or webhook ID in a public log or issue. The registration API requires bearer authentication; subsequent sensor requests use a per-device webhook URL, which must also be treated as a secret.

## Registration

`POST /api/desktop_app/registrations` with `Authorization: Bearer <token>` and `Content-Type: application/json`. The body must be a JSON object with nonempty `device_id` and `device_name` strings (up to 128 characters). Optional strings: `manufacturer`, `model`, `os_name`, `os_version`, `app_version`. Success returns `{"success":true,"webhook_id":"…"}`. Registering an existing `device_id` returns its existing webhook to its owner or a HA admin; an unrelated non-admin receives 403. Keep the device ID stable across upgrades to retain entities.

`GET /api/desktop_app/ping` is unauthenticated and returns 200 when the API has loaded. It is only a reachability check. `GET /api/desktop_app/registrations` requires the same bearer token as registration and, from version 1.0.11, returns `integration_version` from HA's loaded integration manifest. Older versions omit that field, so the desktop displays the version as unknown. `POST /api/desktop_app/update` is authenticated and emits the supplied JSON object as a HA event; the desktop sensor flow uses the webhook instead.

## Webhook

Send `POST /api/webhook/<webhook_id>` with a JSON object containing `"protocol_version":1`, a `type`, and a `data` object. Older clients may omit `protocol_version`; unsupported explicit versions receive 400. Successful command replies contain `"success":true` and `"protocol_version":1`. An unknown device webhook receives 410. The desktop must check the HTTP status **and** the success acknowledgement.

- `register_sensor`: `data` requires `sensor_unique_id`, `sensor_name`, and `sensor_type` (`sensor` or `binary_sensor`). Optional fields include `sensor_state`, `sensor_attributes`, `sensor_icon`, `sensor_device_class`, `sensor_unit_of_measurement`, `sensor_state_class`, `sensor_entity_category`, and boolean `update_at_interval`. Register before updating. Re-registering the same sensor updates its metadata without changing its unique ID. A device may register at most 512 sensors.
- `update_sensor_states`: `data.sensors` is a list of registered sensor IDs with optional scalar `sensor_state`, `sensor_attributes` object, and `sensor_icon`. The list may contain at most 512 distinct sensors; unknown or duplicate IDs are rejected before updating heartbeat or measurements. `update_interval`, when supplied, must be 5–3600 seconds. Optional `snapshot_scope` is `dynamic` or `all`: omitted registered readings within that scope become unavailable. Older clients that omit the scope do not clear omitted readings.
- `update_registration`: updates `device_name`, `os_version`, or `app_version` for the same device.
- `device_offline`: marks the device offline immediately on graceful shutdown. Otherwise availability expires after missed heartbeats according to the registered update interval.

States must be scalar JSON values or `null`; `null` means unavailable. Do not send `NaN` or infinity. Attributes must be JSON objects. `system_uptime` remains numeric seconds and may include a `human_readable` attribute for display. Entity IDs are maintained by retaining device and sensor unique IDs; do not delete an existing HA device to force a refresh.

The [installation guide](INSTALLATION.md) covers deployment, dashboard configuration and rollback. Contract tests in `tests/` cover accepted and rejected payloads, but the release also requires a live Home Assistant upgrade test.
