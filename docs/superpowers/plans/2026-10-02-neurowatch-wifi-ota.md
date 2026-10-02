# NeuroWatch Wi-Fi OTA Implementation Plan

## Goal
Implement a local iPhone/Safari firmware updater on branch `neurowatch-wifi-ota` while preserving USB/recovery updating.

## Task 1 — OTA service contract tests
- Add `tests/test_neurowatch_wifi_ota.py`.
- Assert Wi-Fi is OFF during normal setup.
- Assert a `WIFI UPDATE` menu item exists.
- Assert SoftAP address `192.168.4.1` and an HTTP update endpoint exist.
- Assert `Update.begin`, `Update.write`, `Update.end(true)` and restart only after successful finalization.
- Assert existing USB/recovery code remains present.
- Run tests and confirm the new OTA assertions initially fail.

## Task 2 — Wi-Fi OTA implementation
- Add the minimal ESP32 HTTP server / Update dependencies already available in the ESP32 Arduino environment.
- Implement service-mode state, AP SSID/password generation, web page, `/status`, `/update`, and guarded reboot handling.
- Stream multipart upload into the inactive OTA partition.
- Reject empty/failed/oversized uploads and abort safely.
- Restart only after `Update.end(true)` succeeds.
- Keep Wi-Fi disabled during ordinary boot.

## Task 3 — Watch UI integration
- Add `WIFI UPDATE` to the existing settings menu.
- Add a dedicated service screen showing SSID, password, `192.168.4.1`, and concise iPhone instructions.
- Ensure normal button handling does not accidentally trigger service actions.
- Keep existing USB/update diagnostic screens untouched.

## Task 4 — Safety and power behavior
- Stop the web server and SoftAP on service exit/error where possible.
- Avoid Wi-Fi work in the normal watch loop.
- Ensure repeated upload attempts cannot select a partially written image.
- Keep current image bootable on every failure path.

## Task 5 — CI and build verification
- Extend the existing NeuroWatch GitHub Actions workflow with OTA contract tests.
- Compile with ESP32 2.0.15, Watchy 1.4.7, and current partition scheme.
- Verify the resulting `.bin` exists and fits the OTA application partition.
- Produce `NeuroWatch-OS-v0.10-wifi-ota.bin` and SHA256 checksum.
- Report branch, commit, CI run, artifact, and iPhone usage steps.

## Constraints
- Do not modify `main`.
- Preserve CH9102/CdcAcmSerialDriver USB path.
- No cloud OTA and no remote firmware download.
- No continuous Wi-Fi operation in normal mode.
- Keep UI inside 200x200 and avoid overlap.
