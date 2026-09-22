# NeuroWatch OS — Cyber Terminal (Watchy V2)

This repository is a **development prototype**, not verified firmware for a physical watch.

Target inferred from device screenshots: ESP32-PICO-D4, 4 MB flash, RTC PCF8563, 200×200 E-Paper, Watchy library 1.4.6. The actual factory flash partition table and recovery path are **unknown**. The factory WiFiManager upload form is not proof that a valid second OTA partition is available.

## Development workflow (iPhone only)

GitHub Actions compiles a **candidate app-only ESP32 image**. A successful build is **not** permission to flash it: first identify actual running/next OTA partitions and arrange a verified USB recovery and factory backup. Do not upload source ZIP, bootloader or partition table to the watch. **Do not attempt BLE OTA** on this device; it previously became unresponsive until battery reconnection.

The watch code preserves deep sleep, handles four physical buttons, provides three E-Paper faces and a button-activated Wi-Fi portal with a random access-point password. The portal is for later updates **only if** the installed partition table has two valid physical OTA app slots and the battery voltage is sufficient. It does not add OTA slots to the factory layout.

Sources: [upstream Watchy v1.4.7](https://github.com/sqfmi/Watchy/tree/v1.4.7), [ESP32 Arduino 2.0.15](https://github.com/espressif/arduino-esp32/tree/2.0.15), [WiFiManager 2.0.17](https://github.com/tzapu/WiFiManager/tree/v2.0.17).

Do not embed passwords, personal information or API keys in this public repository. Firmware is experimental until a hardware run and safe rollback are verified.
