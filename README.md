# Desktop App integration for Home Assistant

This repository contains the Home Assistant custom integration for the [Home Assistant Companion desktop app](https://github.com/Fill84/HA-Companion-App). It receives device registration through an authenticated API and sensor updates through per-device webhooks. The integration keeps registered entity identifiers across upgrades and marks missing live readings unavailable.

Version **1.0.11** is [published for HACS](https://github.com/Fill84/ha-integration/releases/tag/1.0.11). Its upgrade from HACS 1.0.10 was tested on Home Assistant 2026.9.3 with two connected Windows desktops and all 109 existing Desktop App entity identities preserved. Home Assistant 2026.9.0 remains the declared minimum; other versions have not yet been tested in a compatibility matrix.

## Install and upgrade

Read the [installation, upgrade, dashboard and rollback guide](docs/INSTALLATION.md). In brief: add `https://github.com/Fill84/ha-integration` as a HACS custom **Integration** repository, install the compatible release, and fully restart Home Assistant. Version 1.0.12 lets each 1.0.6 desktop create its own HA device entry with an administrator token; no empty hub or manual Add action is needed. The published 1.0.11 integration still requires the documented hub activation until 1.0.12 is released. Preserve existing device entries and entity IDs during upgrades.

The desktop app registers sensors before sending state batches. It sends wire protocol version 1; older desktop clients that omit the version remain supported. See the [protocol reference](docs/PROTOCOL.md) for endpoints, payloads and error behavior. The numeric `system_uptime` state stays in seconds for automations and statistics. Its `human_readable` attribute can be shown in a dashboard Entities card without changing the entity ID.

## Verify

`GET /api/desktop_app/ping` should return HTTP 200 after Home Assistant starts. A 200 response confirms that the integration API is loaded; it does not prove that a desktop has registered or sent readings. Check the device's Online entity and several measured entities for the end-to-end result.

For local contract tests, run `python -m pytest -q` from this repository. These tests use Home Assistant boundary stubs; installed Home Assistant and HACS upgrade tests remain release requirements.

See [CHANGELOG.md](CHANGELOG.md) for changes and the [desktop verification status](https://github.com/Fill84/HA-Companion-App/blob/main/docs/plans/2026-09-24-verificatiestatus.md) for remaining release checks.
