#pragma once

#define NW_VERSION "0.7"

// Persistent UI defaults used only when no saved preference exists.
#define NW_DEFAULT_24H 1
#define NW_DEFAULT_DMY 1
#define NW_DEFAULT_VIBRATION 1
#define NW_DEFAULT_HOURLY_BUZZ 0

// Watch-face behaviour.
#define NW_STEP_GOAL 8000UL
#define NW_MENU_VISIBLE_ROWS 5
#define NW_EDITOR_TIMEOUT_MS 30000UL

// Kept for Watchy's base settings; normal daily operation does not start Wi-Fi/BLE.
#define NW_UTC_OFFSET_SECONDS (5 * 3600)
