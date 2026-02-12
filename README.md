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

1. Add this repository as a custom repository in HACS
2. Search for "Desktop App" and install
3. Restart Home Assistant

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

## API Endpoints

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
   - Na herstart zou in de HA-log moeten staan: `Registered Desktop App registration endpoint at /api/desktop_app/registrations`.
   - Staat daar een fout over `hass.http not available`, dan laadt de http-integratie niet goed.

4. **URL in de app**
   - Gebruik de basis-URL van HA **zonder** `/api` erachter (bijv. `https://ha.jouwdomein.nl` of `http://192.168.1.10:8123`).

## License

MIT

# Integratie branch README

Deze branch bevat alleen de Home Assistant custom integratie voor HACS/custom repository.

Gebruik deze branch als custom repository in HACS:
- Voeg toe via HACS: https://github.com/Fill84/HA-Companion-App
- De integratie bevindt zich in custom_components/desktop_app

Zie ook hacs.json en README.md voor instructies.
