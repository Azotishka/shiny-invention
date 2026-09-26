# NeuroWatch Phone Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a stronger configurable alarm vibration and foreground BLE time synchronization from iPhone or Android with UTC+05:00 as the initial offset.

**Architecture:** Keep BLE off during normal sleep. A watch menu action starts a 60-second GATT server window; native Android and iOS clients write one validated local-time packet and read the result. Portable firmware policy helpers are host-tested independently.

**Tech Stack:** Arduino ESP32 2.0.15, Watchy 1.4.7, C++11, Kotlin/Android BLE GATT, SwiftUI/CoreBluetooth, Swift Package Manager, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-27-neurowatch-phone-sync-design.md`

## Global Constraints

- Preserve app-only firmware flashing; never write the bootloader or partition table.
- Keep Wi-Fi and Bluetooth disabled at rest; sync advertising lasts at most 60 seconds.
- Accept only the 15-byte version-1 time packet, with CRC-16/CCITT-FALSE and validated fields.
- Default timezone offset is UTC+05:00; Android API floor is 26 and iOS floor is 16.
- Alarm vibration is independently configurable and alarm remains disabled by default.

## Review Focus

- Malformed BLE packets must not change RTC fields or saved timezone offset.
- Repeated redraws in the same minute must not vibrate the alarm twice on one day.
- BLE startup, cancellation, success, and timeout must all stop advertising and deinitialize Bluetooth.
- Phone timezone offsets west of UTC must retain their signed two-byte representation.
- A phone that loses permission or disconnects must receive a clear error and allow retry.

---

### Task 1: Portable firmware policy and packet validation

**Files:**
- Create: `firmware/NeuroWatch_OS/alarm_policy.h`
- Create: `firmware/NeuroWatch_OS/time_sync_packet.h`
- Create: `scripts/test_watch_logic.py`

**Interfaces:**
- `nwShouldFireDailyAlarm(...)` returns true once at the configured local minute per day stamp.
- `nwShouldVibrateAlarm(triggered, enabled)` gates haptic output independently.
- `nwDecodeTimeSyncPacket(bytes, length, result)` accepts only a valid fixed packet.

- [x] Write host-compiled behavior tests first.
- [x] Run tests and confirm they fail because production helpers are missing.
- [x] Implement the minimal portable headers.
- [x] Run `python3 -m unittest scripts/test_watch_logic.py -v`.

### Task 2: Watch UI, persistence, alarm haptics, and low-power BLE server

**Files:**
- Modify: `firmware/NeuroWatch_OS/NeuroWatch_OS.ino`
- Modify: `firmware/NeuroWatch_OS/neuro_config.h`
- Modify: `scripts/test_firmware_safety.py`

**Interfaces:**
- `syncPhoneTime()` advertises the shared service only on explicit request.
- `nwUtcOffsetMinutes` stores the last accepted signed offset in minutes.
- `nwAlarmVibration` controls the alarm's two-burst pattern, separate from button buzz.

- [x] Add failing safety checks for independent alarm vibration, sync lifetime, timezone persistence, and RTC updates.
- [x] Implement settings/menu integration and bounded BLE session.
- [ ] Run the entire Python suite and compile the firmware in CI.

### Task 3: Android NeuroWatch Connect client

**Files:**
- Create: `mobile/android/app/src/main/java/ru/neurogazette/neurowatchconnect/TimeSyncPacket.kt`
- Create: `mobile/android/app/src/main/java/ru/neurogazette/neurowatchconnect/MainActivity.kt`
- Create: `mobile/android/app/src/test/java/ru/neurogazette/neurowatchconnect/TimeSyncPacketTest.kt`
- Create: Android Gradle project and manifest.

**Interfaces:**
- `TimeSyncPacket.encode(LocalDateTime, utcOffsetMinutes)` emits the exact 15-byte protocol packet.
- Activity scans for the service UUID, writes the time packet, polls status, and cleans up GATT.

- [x] Add the fixed golden-vector JUnit test before the encoder.
- [x] Implement packet encoding, permission handling, scan/connect/write/read flow, and retry status.
- [ ] Run `gradle :app:testDebugUnitTest :app:assembleDebug`.

### Task 4: iOS NeuroWatch Connect client

**Files:**
- Create: `mobile/ios/NeuroWatchProtocol` Swift package and golden-vector test.
- Create: `mobile/ios/Sources/BluetoothSyncManager.swift`
- Create: `mobile/ios/Sources/NeuroWatchConnectApp.swift`
- Create: `mobile/ios/project.yml` and `Info.plist`.

**Interfaces:**
- `TimeSyncPacket.encode(...)` emits the same 15-byte packet as firmware and Android.
- `BluetoothSyncManager` scans, connects, writes local phone time, reads watch status, and supports cancellation.

- [x] Add the fixed golden-vector Swift test before the encoder.
- [x] Implement packet encoding and the foreground CoreBluetooth flow.
- [ ] Run `swift test` and compile the simulator target through XcodeGen.

### Task 5: CI packaging and user instructions

**Files:**
- Create: `.github/workflows/neurowatch-connect-build.yml`
- Create: `mobile/README.md`
- Update: root project README to describe v0.9 and remove stale no-sync claims.

- [ ] Run Python tests, firmware compile, OTA image check, Android tests/APK build, Swift tests, and iOS simulator build.
- [ ] Verify the produced APK, firmware image, and Xcode source package are present.
- [ ] Publish the implementation branch with install instructions and verification status.
