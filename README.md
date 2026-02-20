# Desktop App - Home Assistant Custom Integration

![Integration icon](icons/icon.png)

A custom Home Assistant integration that enables desktop computers to send system sensor data (CPU, GPU, RAM, disk, network, battery) to Home Assistant via webhooks.

## Features

- **Device Registration**: Desktop apps register via REST API with Long-Lived Access Token authentication
- **Webhook-based Updates**: After registration, all sensor updates use webhooks (no per-request auth needed)
- **Dynamic Sensor Creation**: Sensors are created automatically when the desktop app registers them
- **Device Registry**: Full device registry support with manufacturer, model, OS info
- **Persistence**: Sensor states are restored after HA restarts
- **Multi-language**: UI strings available in English and Dutch

## Installation

### HACS (Recommended)

1. In HACS: **Integrations** → **⋮** (menu) → **Custom repositories**
2. Add repository URL: `https://github.com/Fill84/ha-integration` and choose type **Integration**
3. Search for "Desktop App" or "Desktop App Companion" and click **Download**
4. **Fully restart Home Assistant** (not just "Reload Configuration")

**Verify the integration loaded correctly**

- After restart: **Settings** → **System** → **Logs**. Look for:
  - `Desktop App integration loading` → the integration is loaded
  - `Registered Desktop App API at /api/desktop_app/registrations and /api/desktop_app/ping` → the API routes are active
- Test in the browser (no login required): `https://YOUR_HA_URL/api/desktop_app/ping` → **200** with message "Desktop App integration is loaded" = integration is reachable
- Test registration endpoint: `https://YOUR_HA_URL/api/desktop_app/registrations` → **401** means the route is working (token required)

### Manual

1. Copy the `custom_components/desktop_app/` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Setup

This integration is configured automatically when a Desktop Companion App connects. No manual setup is required.

1. Install the Desktop Companion App on your computer
2. In the app settings, enter your Home Assistant URL and a Long-Lived Access Token
3. The integration and device will appear automatically in Home Assistant

## Supported Sensors

| Sensor           | Type                     | Update       |
|------------------|--------------------------|--------------|
| CPU Usage        | sensor (%)               | Interval     |
| CPU Speed        | sensor (MHz)             | Interval     |
| CPU Temperature  | sensor (°C)              | Interval     |
| CPU Model        | sensor                   | Startup only |
| GPU Usage        | sensor (%)               | Interval     |
| GPU Temperature  | sensor (°C)              | Interval     |
| GPU VRAM Used    | sensor (GB)              | Interval     |
| GPU Model        | sensor                   | Startup only |
| RAM Usage        | sensor (%)               | Interval     |
| RAM Used         | sensor (GB)              | Interval     |
| Disk Usage       | sensor (%) per partition | Interval     |
| Network Speed    | sensor (bytes/s)         | Interval     |
| Battery Level    | sensor (%)               | Interval     |
| Battery Charging | binary_sensor            | Interval     |
| OS Version       | sensor                   | Startup only |
| Hostname         | sensor                   | Startup only |
| BIOS Version     | sensor                   | Startup only |
| Motherboard      | sensor                   | Startup only |

## API Endpoints (details)

### Ping (health check)

```
GET /api/desktop_app/ping
```
No authentication required. Returns 200 with a message if the integration is loaded. Useful for testing whether the integration is reachable (also via reverse proxy).

### Registration

```
POST /api/desktop_app/registrations
Authorization: Bearer <long-lived-access-token>
Content-Type: application/json

{
  "device_id": "uuid-string",
  "device_name": "My Desktop",
  "manufacturer": "Dell",
  "model": "XPS 15",
  "os_name": "Windows",
  "os_version": "11",
  "app_version": "1.0.0"
}
```

### Webhook (Register Sensor)

```
POST /api/webhook/<webhook_id>
Content-Type: application/json

{
  "type": "register_sensor",
  "data": {
    "sensor_unique_id": "cpu_usage",
    "sensor_name": "CPU Usage",
    "sensor_type": "sensor",
    "sensor_state": 45.2,
    "sensor_device_class": null,
    "sensor_unit_of_measurement": "%",
    "sensor_state_class": "measurement",
    "sensor_icon": "mdi:cpu-64-bit"
  }
}
```

### Webhook (Update Sensor States)

```
POST /api/webhook/<webhook_id>
Content-Type: application/json

{
  "type": "update_sensor_states",
  "data": {
    "sensors": [
      {
        "sensor_unique_id": "cpu_usage",
        "sensor_state": 67.3,
        "sensor_attributes": {}
      }
    ]
  }
}
```

## Troubleshooting

### "404" on `/api/desktop_app/ping` or `/api/desktop_app/ping/`

- **Trailing slash**: Both `/api/desktop_app/ping` and `/api/desktop_app/ping/` are supported. If you used another path, try one of these.
- **Route not registered**: If you still get 404, the integration may not be loading. In **Settings → System → Logs** look for:
  - `Registered Desktop App API at /api/desktop_app/registrations and /api/desktop_app/ping` → routes are active.
  - If that line is missing after a full restart, the integration did not register (wrong path, or `hass.http` not ready). Ensure the integration is in `config/custom_components/desktop_app/` and do a **full** Home Assistant restart.

### "Registration failed (404 Not Found)"

The 404 means the registration endpoint is not reachable. Check the following:

1. **Integration installed and HA restarted**
   - The custom component must be in `config/custom_components/desktop_app/` (or installed via HACS).
   - After installation, **fully restart Home Assistant** (not just reload configuration).

2. **Test the endpoint**
   - Open in the browser: `https://YOUR_HA_URL/api/desktop_app/registrations`
   - **401 Unauthorized** = the route exists; authentication is required (the app uses a token).
   - **404 Not Found** = the integration is not loaded or the route is not registered.

3. **Check the logs**
   - After restart, the HA log should contain: `Registered Desktop App API at /api/desktop_app/registrations and /api/desktop_app/ping`.
   - If there is an error about `hass.http not available`, the HTTP integration is not loading correctly.

4. **URL in the app**
   - Use the base URL of HA **without** `/api` appended (e.g. `https://ha.yourdomain.com` or `http://192.168.1.10:8123`).

5. **Reverse proxy (nginx, Caddy, etc.)**
   - Make sure the `/api/` path is forwarded to Home Assistant. If this mapping is missing, you will get 404 on all `/api/...` requests.

6. **Firewall**
   - **404** = the server (HA or proxy) responds but does not recognize the route → see points 1–5.
   - **No connection / timeout** = often a firewall or network issue: make sure the HA port (e.g. 8123) or your reverse proxy is reachable from the desktop PC. Windows Firewall, router, or corporate firewall may block outgoing traffic. Test in the browser on the same PC: `http://YOUR_HA_IP:8123/api/desktop_app/ping`.

## API Endpoints (overview)

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /api/desktop_app/ping` | No | Check if the integration is loaded and reachable (returns 200 + message) |
| `POST /api/desktop_app/registrations` | Bearer token | App registration |
| `POST /api/webhook/<webhook_id>` | No (webhook ID in path) | Sensor data / webhook commands |

## License

MIT

# Integration branch README

This branch contains only the Home Assistant custom integration for HACS/custom repository.

Use this branch as a custom repository in HACS:
- Add via HACS: https://github.com/Fill84/HA-Companion-App
- The integration is located in custom_components/desktop_app

See also hacs.json and README.md for instructions.

