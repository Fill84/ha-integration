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
2. Add repository URL: `https://github.com/Fill84/ha-integration` en kies type **Integration**
3. Zoek "Desktop App" of "Desktop App Companion" en klik **Download**
4. **Herstart Home Assistant volledig** (niet alleen "Configuratie herladen")

**Controleren of de integratie goed is geladen**

- Na herstart: **Instellingen** → **Systeem** → **Logboeken**. Zoek naar:
  - `Desktop App integration loading` → de integratie is geladen
  - `Registered Desktop App API at /api/desktop_app/registrations and /api/desktop_app/ping` → de API-routes zijn actief
- Test in de browser (geen inlog nodig): `https://JOUW_HA_URL/api/desktop_app/ping` → **200** met bericht "Desktop App integration is loaded" = integratie bereikbaar
- Test registratie-endpoint: `https://JOUW_HA_URL/api/desktop_app/registrations` → **401** betekent dat de route werkt (token vereist)

### Manual

1. Copy the `custom_components/desktop_app/` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Setup

This integration is configured automatically when a Desktop Companion App connects. No manual setup is required.

1. Install the Desktop Companion App on your computer
2. In the app settings, enter your Home Assistant URL and a Long-Lived Access Token
3. The integration and device will appear automatically in Home Assistant

## Supported Sensors

| Sensor | Type | Update |
|--------|------|--------|
| CPU Usage | sensor (%) | Interval |
| CPU Speed | sensor (MHz) | Interval |
| CPU Temperature | sensor (°C) | Interval |
| CPU Model | sensor | Startup only |
| GPU Usage | sensor (%) | Interval |
| GPU Temperature | sensor (°C) | Interval |
| GPU VRAM Used | sensor (GB) | Interval |
| GPU Model | sensor | Startup only |
| RAM Usage | sensor (%) | Interval |
| RAM Used | sensor (GB) | Interval |
| Disk Usage | sensor (%) per partition | Interval |
| Network Speed | sensor (bytes/s) | Interval |
| Battery Level | sensor (%) | Interval |
| Battery Charging | binary_sensor | Interval |
| OS Version | sensor | Startup only |
| Hostname | sensor | Startup only |
| BIOS Version | sensor | Startup only |
| Motherboard | sensor | Startup only |

## API Endpoints (details)

### Ping (health check)

```
GET /api/desktop_app/ping
```
Geen authenticatie. Returns 200 met bericht als de integratie geladen is. Handig om te testen of de integratie bereikbaar is (ook via reverse proxy).

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

De 404 betekent dat het registratie-endpoint niet bereikbaar is. Controleer het volgende:

1. **Integratie geïnstalleerd en HA herstart**
   - De custom component moet in `config/custom_components/desktop_app/` staan (of via HACS geïnstalleerd zijn).
   - Na installatie **Home Assistant volledig herstarten** (niet alleen configuratie herladen).

2. **Endpoint testen**
   - Open in de browser: `https://JOUW_HA_URL/api/desktop_app/registrations`
   - **401 Unauthorized** = de route bestaat; je moet inloggen (de app gebruikt een token).
   - **404 Not Found** = de integratie is niet geladen of de route is niet geregistreerd.

3. **Logs controleren**
   - Na herstart zou in de HA-log moeten staan: `Registered Desktop App API at /api/desktop_app/registrations and /api/desktop_app/ping`.
   - Staat daar een fout over `hass.http not available`, dan laadt de http-integratie niet goed.

4. **URL in de app**
   - Gebruik de basis-URL van HA **zonder** `/api` erachter (bijv. `https://ha.jouwdomein.nl` of `http://192.168.1.10:8123`).

5. **Reverse proxy (nginx, Caddy, enz.)**
   - Zorg dat het pad `/api/` naar Home Assistant wordt doorgestuurd. Ontbreekt die mapping, dan krijg je 404 op alle `/api/...`-requests.

6. **Firewall**
   - **404** = de server (HA of proxy) antwoordt maar kent de route niet → zie punten 1–5.
   - **Geen verbinding / timeout** = vaak firewall of netwerk: zorg dat de poort van HA (bijv. 8123) of je reverse proxy vanaf de desktop-PC bereikbaar is. Windows Firewall, router of bedrijfsfirewall kunnen uitgaand verkeer blokkeren. Test in de browser op dezelfde PC: `http://JOUW_HA_IP:8123/api/desktop_app/ping`.

## API Endpoints (overzicht)

| Endpoint | Auth | Doel |
|----------|------|------|
| `GET /api/desktop_app/ping` | Nee | Controleren of de integratie geladen en bereikbaar is (geeft 200 + bericht) |
| `POST /api/desktop_app/registrations` | Bearer token | App-registratie |
| `POST /api/webhook/<webhook_id>` | Nee (webhook-id in pad) | Sensordata / webhook-commando’s |

## License

MIT

# Integratie branch README

Deze branch bevat alleen de Home Assistant custom integratie voor HACS/custom repository.

Gebruik deze branch als custom repository in HACS:
- Voeg toe via HACS: https://github.com/Fill84/HA-Companion-App
- De integratie bevindt zich in custom_components/desktop_app

Zie ook hacs.json en README.md voor instructies.
