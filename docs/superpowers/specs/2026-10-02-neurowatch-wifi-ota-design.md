# NeuroWatch Wi-Fi OTA Update Design

**Date:** 2026-10-02

## Goal

Add a safe local Wi-Fi firmware-update mode to NeuroWatch OS so an iPhone can update the watch from Safari without USB, while preserving the existing USB/recovery update path.

## Approved user flow

1. On the watch, open Settings and select **WIFI UPDATE**.
2. The watch stops normal operation and starts a temporary Wi-Fi access point.
3. The display shows the temporary SSID, password, and local address.
4. On iPhone, connect to that Wi-Fi network and open Safari at **http://192.168.4.1/**.
5. Safari shows a compact NeuroWatch update page with current OS version and a firmware file picker.
6. The user selects a NeuroWatch `.bin` firmware file and starts the upload.
7. The watch streams the upload directly into the inactive OTA application partition.
8. The watch verifies the update write, marks the new image as the next boot image, and restarts.
9. If upload or validation fails, the running firmware remains active and the watch returns to the update page/error state without changing the boot image.

## Architecture

### Wi-Fi service mode

Normal boot continues to disable Wi-Fi and Bluetooth for power saving. Wi-Fi is enabled only after the user explicitly enters **WIFI UPDATE**.

The update mode uses ESP32 SoftAP mode rather than requiring an existing home/phone network. This is important for iPhone-only operation because the watch can provide the temporary network itself.

The AP uses a unique SSID based on the watch MAC suffix, for example:

- SSID: `NeuroWatch-A1B2C3`
- Password: generated from the same device-specific suffix using a fixed NeuroWatch prefix.

The password is shown on the watch while update mode is active. It is not stored as a user-editable secret and is not used during normal operation.

### Local web server

The firmware hosts a small HTTP server in AP mode:

- `GET /` — update UI.
- `POST /update` — multipart firmware upload.
- `GET /status` — JSON status containing current version, device id, and update-mode state.
- `GET /reboot` — guarded restart endpoint for service use.

The web UI is embedded in firmware flash and uses plain HTML/CSS/JavaScript to avoid additional runtime dependencies.

The upload page must work in current iPhone Safari without a native app.

### OTA write path

Use the ESP32 Arduino `Update` API with the inactive OTA partition. The build continues using the existing `min_spiffs` partition scheme, which provides OTA slots.

The upload handler:

- accepts only firmware files intended for NeuroWatch,
- streams chunks to `Update.write()`,
- aborts on write errors,
- checks `Update.end(true)`,
- does not call `ESP.restart()` until the upload is completely received and validated,
- leaves the current image selected when any step fails.

No bootloader or partition layout change is required for the current 4 MB Watchy target.

### Watch UI

Add one settings item:

- **WIFI UPDATE**

When selected, the watch shows a service screen with:

- Wi-Fi SSID
- password
- `192.168.4.1`
- short instruction: **CONNECT → OPEN SAFARI → UPLOAD**

The service screen disables normal watch-face actions until the update mode exits.

### Existing USB path

The existing CH9102/CdcAcmSerialDriver USB/update path is not removed, refactored, or made dependent on Wi-Fi. USB remains the recovery/fallback update path.

### Failure behavior

The update service must safely handle:

- no file selected,
- malformed/missing multipart upload,
- zero-byte upload,
- upload larger than the active OTA slot,
- interrupted upload,
- Update write failure,
- Update finalization failure,
- client disconnect,
- repeated upload attempts.

For all failures, the current running firmware remains bootable.

### Power and cleanup

Wi-Fi is off during normal boot. When leaving update mode successfully or after a hard failure, Wi-Fi is stopped before returning to normal Watchy operation.

The server loop is limited to service mode and must not add a continuous Wi-Fi workload to the regular watch loop.

## Security constraints

This is intentionally a local maintenance interface, not a cloud OTA server.

- No internet-facing service.
- No permanent Wi-Fi credentials.
- No remote firmware URL downloads.
- Firmware is supplied by the user from the iPhone.
- Only POST /update can modify the OTA partition.
- The device-specific AP password prevents an arbitrary nearby device from immediately opening the maintenance interface.

## Acceptance criteria

- A 4 MB Watchy/ESP32 build compiles with the pinned ESP32 2.0.15 toolchain.
- The resulting firmware still fits the selected OTA application partition.
- Normal boot keeps Wi-Fi disabled.
- Settings exposes WIFI UPDATE.
- In update mode, the watch creates the documented SoftAP and serves 192.168.4.1.
- Safari can load the update page and select a local .bin file.
- A valid NeuroWatch firmware upload reaches the inactive OTA partition and reboots into the new image.
- A failed/interrupted upload does not replace the current bootable image.
- USB/recovery behavior remains unchanged.
- Automated tests cover the service-mode contract and source-level safety invariants.
