# Changelog

## 1.0.11 — release candidate, not published

- Preserve existing desktop device and entity IDs during sensor refresh and recovery.
- Clear stale sensor readings when a full or dynamic snapshot no longer contains them.
- Keep online/offline state consistent with accepted heartbeats and device shutdown.
- Validate registration and webhook payloads before changing Home Assistant state.
- Reject unknown or duplicate sensor updates and cap registrations per device.
- Add protocol version 1 acknowledgements while accepting legacy unversioned desktop clients.
- Avoid logging the full body of the authenticated update endpoint.

The public HACS repository remains on 1.0.10 until the integration has passed
the Home Assistant upgrade test and the agreed two-computer release gate.
