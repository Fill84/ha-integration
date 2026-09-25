# Changelog

## 1.0.11

- Preserve existing desktop device and entity IDs during sensor refresh and recovery.
- Clear stale sensor readings when a full or dynamic snapshot no longer contains them.
- Keep online/offline state consistent with accepted heartbeats and device shutdown.
- Validate registration and webhook payloads before changing Home Assistant state.
- Reject unknown or duplicate sensor updates and cap registrations per device.
- Add protocol version 1 acknowledgements while accepting legacy unversioned desktop clients.
- Remove the unused authenticated update-event endpoint; measurements continue through device webhooks.
- Require an administrator to claim a legacy device registration that has no recorded owner.
- Test register/update payloads against the same protocol fixture as the desktop app.
- Report the version of the integration actually loaded by Home Assistant to authenticated clients.
