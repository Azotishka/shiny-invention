#pragma once

#define NW_VERSION "1.0"

// Persistent UI defaults used only when no saved preference exists.
#define NW_DEFAULT_24H 1
#define NW_DEFAULT_DMY 1
#define NW_DEFAULT_VIBRATION 1
#define NW_DEFAULT_HOURLY_BUZZ 0
#define NW_DEFAULT_ALARM_ENABLED 0
#define NW_DEFAULT_ALARM_VIBRATION 1
#define NW_DEFAULT_ALARM_HOUR 7
#define NW_DEFAULT_ALARM_MINUTE 0

// Time received from a phone is stored as the watch's local wall clock.
#define NW_DEFAULT_TIMEZONE_MINUTES 300
#define NW_BLE_SYNC_TIMEOUT_MS 60000UL
#define NW_BLE_SERVICE_UUID "7d2ea28a-f7bd-485a-bd9d-92ad6ecfe93e"
#define NW_BLE_TIME_UUID "7d2ea28a-f7bd-485a-bd9d-92ad6ecfe93f"
#define NW_BLE_STATUS_UUID "7d2ea28a-f7bd-485a-bd9d-92ad6ecfe940"

// Watch-face behaviour.
#define NW_STEP_GOAL 8000UL
#define NW_STEP_GOAL_MIN 1000UL
#define NW_STEP_GOAL_MAX 30000UL
#define NW_STEP_GOAL_STEP 500UL
#define NW_STEP_GOAL_HOLD_STEP 2500UL
#define NW_MENU_VISIBLE_ROWS 5
#define NW_EDITOR_TIMEOUT_MS 60000UL
#define NW_WIFI_OTA_TIMEOUT_MS 300000UL

// Kept for Watchy's base settings; normal daily operation does not start Wi-Fi/BLE.
#define NW_UTC_OFFSET_SECONDS (5 * 3600)
