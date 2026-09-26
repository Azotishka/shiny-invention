# NeuroWatch phone sync and alarm design

## Goal

Let NeuroWatch set its date, local time, and current UTC offset from an iPhone or Android phone, while keeping Bluetooth off during normal watch sleep. Make the daily alarm's vibration configurable, testable, and easy to distinguish from button feedback.

## Existing behavior

- The Watchy V2 firmware uses an ESP32-PICO-D4 and an RTC that stores local calendar fields.
- The current alarm already triggers a short motor pattern, but the alarm is disabled by default and its vibration has no separate setting or test action.
- The watch disables Wi-Fi and Bluetooth before its regular low-power cycle.
- The existing Android application is a USB firmware updater, not a BLE companion.

## Chosen design

Add native Android and iOS companion clients that use the same custom BLE GATT service. The user opens **SYNC PHONE TIME** from the watch menu, then taps **Synchronize** in NeuroWatch Connect. The watch advertises for at most 60 seconds and stops BLE after success, cancellation, or timeout. The phone sends its current local date/time and UTC offset; the RTC is set to those local fields and the offset is saved in preferences. The initial offset is UTC+05:00 (Yekaterinburg). A later phone sync updates the offset when the phone's timezone changes.

The 15-byte packet uses `NW`, protocol version `1`, command `1`, year/month/day/hour/minute/second, signed UTC offset in minutes, and CRC-16/CCITT-FALSE. Firmware validates packet length, checksum, calendar date, time fields, year range 2020–2099, and offset range UTC−12:00 through UTC+14:00 before touching the RTC.

The GATT service exposes one write characteristic for the packet and one read/notify characteristic for `READY`, `INVALID`, `OK`, or `ERROR`. The app reports success only after reading `OK` from the watch.

For the alarm, add an independent persisted **ALARM VIBRATION** switch and a **TEST VIBRATION** action. The alarm remains off by default to avoid waking the owner unexpectedly. When enabled, it fires once per local calendar day and runs two clear vibration bursts if alarm vibration is on.

## Constraints and recovery

- BLE is started only from the explicit watch menu action and is shut down on every exit path.
- The BLE characteristic accepts time data only; it does not expose firmware update or arbitrary settings commands.
- Mobile clients operate in the foreground and require the watch to be on its sync screen.
- The watch stores the current offset, not an IANA timezone rule database. Re-sync from the phone after changing timezone or after a daylight-saving transition.
- Android supports API 26 and later. The iOS project targets iOS 16 and later and is run/signed from Xcode on the owner's Mac.

## Verification

Host-compiled C++ tests cover alarm timing and packet validation. Android JUnit and Swift Package tests compare both clients to a fixed byte-for-byte packet. CI compiles the Watchy app, builds the Android APK, runs the iOS protocol tests, and compiles the iOS simulator app.
