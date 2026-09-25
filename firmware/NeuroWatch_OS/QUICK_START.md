# NeuroWatch OS v0.8 — quick controls

## Watch face and menu

- **MENU** opens settings.
- **UP / DOWN** moves through the menu.
- **MENU** opens the selected setting; **BACK** returns to the watch face.
- On the watch face, **UP** opens steps and **DOWN** opens status.

## Setting time and date

- In an editor, tap **UP / DOWN** to change the selected value by one.
- Hold **UP / DOWN** for a larger step: hours by 5, minutes by 10, days by 7, months by 3, and years by 10.
- **MENU** moves to the next field; on the last field, it saves.
- **BACK** cancels. An idle editor cancels after 60 seconds.
- The date editor follows the selected DD.MM or MM/DD format.

## Added tools

- Set a daily vibration alarm and its time. The alarm is haptic; it has no sound.
- Set the step goal from 1,000 to 30,000, in 500-step increments. Holding a button changes it by 2,500.
- Existing settings such as 12/24-hour time, date format, button vibration, and hourly vibration are retained after updating.

## Power and display

- The OS keeps one standard monochrome wallpaper.
- Wi-Fi and Bluetooth remain off during normal use; settings are cached in RTC memory between wakeups.
- Menu/editor screens use partial refreshes, with bounded full refreshes to limit ghosting.

This build targets Watchy V2 with ESP32-PICO-D4 and 4 MB Flash. It is an app-only update; it does not erase Flash or replace the bootloader or partition table.
