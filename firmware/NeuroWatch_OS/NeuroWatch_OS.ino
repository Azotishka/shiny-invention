#include <Arduino.h>
#include <Watchy.h>
#include <WiFiManager.h>
#include <WiFi.h>
#include <Fonts/FreeMonoBold18pt7b.h>
#include <esp_system.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>
#include <Preferences.h>
#include "neuro_config.h"

// Watchy V2 / ESP32-PICO-D4 only. No bootloader or partition-table writes.
// Watchy library supplies RTC, time editor, display and deep sleep.
watchySettings nwSettings{
    .cityID = "",
    .weatherAPIKey = "",
    .weatherURL = "",
    .weatherUnit = "metric",
    .weatherLang = "en",
    .weatherUpdateInterval = 60,
    .ntpServer = "pool.ntp.org",
    .gmtOffset = NW_UTC_OFFSET_SECONDS,
    .vibrateOClock = false,
};

extern bool alreadyInMenu; // RTC retained menu flag from Watchy
RTC_DATA_ATTR uint8_t retainedFace = 255;
RTC_DATA_ATTR uint8_t menuPartialRefreshes = 0;

class NeuroWatch : public Watchy {
 public:
  using Watchy::Watchy;

  void drawWatchFace() override {
    display.setFullWindow();
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
    display.setTextWrap(false);
    display.drawRect(0, 0, DISPLAY_WIDTH, DISPLAY_HEIGHT, GxEPD_BLACK);
    display.drawLine(5, 22, 194, 22, GxEPD_BLACK);
    label(7, 7, "NW://CYBER TERMINAL");
    if (retainedFace == 2) diagnostics();
    else timePanel();
    display.drawLine(5, 178, 194, 178, GxEPD_BLACK);
    label(7, 186, "NW v0.4   MENU: OPTIONS");
  }

  void setFace(uint8_t face) { retainedFace = face <= 2 ? face : 0; }

  void handleButtonPress() override {
    const uint64_t pressed = esp_sleep_get_ext1_wakeup_status();
    if (guiState == WATCHFACE_STATE) {
      if (pressed & MENU_BTN_MASK) {
        menuIndex = 0;
        showNeuroMenu();
      }
    } else if (guiState == MAIN_MENU_STATE) {
      if (pressed & BACK_BTN_MASK) {
        RTC.read(currentTime);
        showWatchFace(false);
      } else if (pressed & UP_BTN_MASK) {
        menuIndex = (menuIndex + 4) % 5;
        showNeuroMenu(true);
      } else if (pressed & DOWN_BTN_MASK) {
        menuIndex = (menuIndex + 1) % 5;
        showNeuroMenu(true);
      } else if (pressed & MENU_BTN_MASK) {
        if (menuIndex <= 2) {
          const uint8_t previous = retainedFace;
          setFace((uint8_t)menuIndex);
          if (previous != retainedFace) {
            Preferences prefs;
            if (prefs.begin("nw-os", false)) {
              prefs.putUChar("face", retainedFace);
              prefs.end();
            }
          }
          RTC.read(currentTime);
          showWatchFace(false);
        } else if (menuIndex == 3) {
          setTime();
          RTC.read(currentTime);
          showWatchFace(false);
        } else {
          runSafeUpdater();
        }
      }
    } else {
      // Intentionally avoid Watchy's legacy BLE updater.
      RTC.read(currentTime);
      showWatchFace(false);
    }
    // Wait for the released key before Watchy's deep-sleep button wake.
    const uint32_t deadline = millis() + 2500;
    pinMode(MENU_BTN_PIN, INPUT);
    pinMode(BACK_BTN_PIN, INPUT);
    pinMode(UP_BTN_PIN, INPUT);
    pinMode(DOWN_BTN_PIN, INPUT);
    while (digitalRead(MENU_BTN_PIN) || digitalRead(BACK_BTN_PIN) ||
           digitalRead(UP_BTN_PIN) || digitalRead(DOWN_BTN_PIN)) {
      if ((int32_t)(millis() - deadline) >= 0) break;
      delay(10);
    }
  }

 private:
  void showNeuroMenu(bool requestPartial = false) {
    static const char *const items[5] = {
        "TERMINAL", "MINIMAL", "DIAGNOSTICS", "SET CLOCK", "WIFI UPDATE"};
    display.setFullWindow();
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
    display.setTextWrap(false);
    label(7, 8, "NW://MENU  M:OK B:BACK");
    display.drawLine(4, 22, 195, 22, GxEPD_BLACK);
    for (int i = 0; i < 5; ++i) {
      if (i == menuIndex)
        display.fillRect(4, 29 + i * 27, 192, 23, GxEPD_BLACK);
      display.setTextColor(i == menuIndex ? GxEPD_WHITE : GxEPD_BLACK);
      label(8, 36 + i * 27, items[i]);
    }
    display.setTextColor(GxEPD_BLACK);
    // Fast partial update during navigation; full refresh every seventh step
    // to limit E-Paper ghosting and avoid a slow full refresh on every key.
    const bool partial = requestPartial && menuPartialRefreshes < 6;
    menuPartialRefreshes = partial ? menuPartialRefreshes + 1 : 0;
    display.display(partial);
    guiState = MAIN_MENU_STATE;
    alreadyInMenu = false;
  }

  void label(int x, int y, const char *s) {
    display.setFont(nullptr);
    display.setTextSize(1);
    display.setCursor(x, y);
    display.print(s);
  }
  void textRow(int y, const char *s) { label(7, y, s); }

  void timePanel() {
    char buf[30];
    snprintf(buf, sizeof(buf), "%02u:%02u",
             (unsigned)currentTime.Hour, (unsigned)currentTime.Minute);
    display.setFont(&FreeMonoBold18pt7b);
    display.setCursor(7, 61);
    display.print(buf);
    snprintf(buf, sizeof(buf), "%02u/%02u/%04d",
             (unsigned)currentTime.Day, (unsigned)currentTime.Month,
             tmYearToCalendar(currentTime.Year));
    textRow(73, buf);
    display.drawLine(5, 88, 194, 88, GxEPD_BLACK);
    if (retainedFace == 1) {
      textRow(106, "[ TERMINAL MINIMAL ]");
      textRow(134, "MENU  : SETTINGS");
      textRow(149, "BACK  : NO ACTION");
    } else {
      textRow(99, "[ SYS MONITOR ]");
#if NW_SHOW_VOLTAGE
      batteryRow(buf, sizeof(buf), 117);
#endif
#if NW_SHOW_HEAP
      snprintf(buf, sizeof(buf), "HEAP: %lu B",
               (unsigned long)esp_get_free_heap_size());
      textRow(135, buf);
#endif
#if NW_SHOW_WIFI_SAVED
      textRow(153, "WIFI: OFF / ON DEMAND");
#endif
    }
  }

  void diagnostics() {
    char buf[30];
    textRow(31, "[ DEVICE STATUS ]");
    snprintf(buf, sizeof(buf), "RTC : %02u:%02u",
             (unsigned)currentTime.Hour, (unsigned)currentTime.Minute);
    textRow(49, buf);
    batteryRow(buf, sizeof(buf), 67);
    snprintf(buf, sizeof(buf), "HEAP: %lu B",
             (unsigned long)esp_get_free_heap_size());
    textRow(85, buf);
    snprintf(buf, sizeof(buf), "FLASH: %lu MB",
             (unsigned long)(ESP.getFlashChipSize() / (1024UL * 1024UL)));
    textRow(103, buf);
    textRow(121, safeOtaPartition() ? "OTA: SLOT DETECTED" : "OTA: NO DUAL SLOT");
    textRow(139, "RADIO: OFF AT REST");
  }

  // Printing floating-point values each minute adds code and CPU work.
  // Convert once to centivolts, then use integer-only formatting.
  void batteryRow(char *buf, size_t bufSize, int y) {
    const float voltage = getBatteryVoltage();
    if (!(voltage >= 0.0f && voltage <= 6.0f)) {
      textRow(y, "BAT: SENSOR ERROR");
      return;
    }
    const unsigned centivolts = (unsigned)(voltage * 100.0f + 0.5f);
    snprintf(buf, bufSize, "BAT: %u.%02u V", centivolts / 100, centivolts % 100);
    textRow(y, buf);
  }

  const esp_partition_t *safeOtaPartition() {
    const uint32_t physical = 4UL * 1024UL * 1024UL;
    if (ESP.getFlashChipSize() != physical) return nullptr;
    const esp_partition_t *a = esp_partition_find_first(
        ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_0, nullptr);
    const esp_partition_t *b = esp_partition_find_first(
        ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_1, nullptr);
    const esp_partition_t *otadata = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_OTA, nullptr);
    const esp_partition_t *next = esp_ota_get_next_update_partition(nullptr);
    const esp_partition_t *running = esp_ota_get_running_partition();
    if (!a || !b || !otadata || otadata->size < 0x2000 ||
        !next || !running) return nullptr;
    if (otadata->address >= physical ||
        otadata->size > physical - otadata->address) return nullptr;
    if (a->address >= physical || b->address >= physical ||
        a->size < NW_MIN_OTA_SLOT_BYTES || b->size < NW_MIN_OTA_SLOT_BYTES ||
        a->size > physical - a->address ||
        b->size > physical - b->address) return nullptr;
    if (a->address < b->address + b->size &&
        b->address < a->address + a->size) return nullptr;
    if ((running->address != a->address && running->address != b->address) ||
        (next->address != a->address && next->address != b->address) ||
        next->address == running->address) return nullptr;
    return next;
  }

  void statusScreen(const char *first, const char *second, const char *third) {
    display.setFullWindow();
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
    display.setTextWrap(false);
    display.setFont(nullptr);
    display.setTextSize(1);
    label(7, 12, "NEUROWATCH // WIFI OTA");
    display.drawLine(5, 25, 194, 25, GxEPD_BLACK);
    label(7, 46, first);
    label(7, 66, second);
    label(7, 86, third);
    display.display(false);
  }

  void runSafeUpdater() {
    const esp_partition_t *slot = safeOtaPartition();
    if (!slot) {
      statusScreen("NO DUAL-OTA PARTITION", "NO UPLOAD ATTEMPTED", "BACK: RETURN TO CLOCK");
      delay(3000);
      RTC.read(currentTime);
      showWatchFace(false);
      return;
    }
    const float voltage = getBatteryVoltage();
    if (!(voltage >= NW_MIN_OTA_VOLTAGE && voltage < 4.35f)) {
      statusScreen("BATTERY CHECK FAILED", "CHARGE WATCH FIRST", "NO UPLOAD ATTEMPTED");
      delay(3000);
      RTC.read(currentTime);
      showWatchFace(false);
      return;
    }

    // Password is random on each invocation. AP not active during normal use.
    WiFi.mode(WIFI_AP);
    char pass[13];
    const char alphabet[] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    for (size_t i = 0; i < 12; ++i)
      pass[i] = alphabet[esp_random() % (sizeof(alphabet) - 1)];
    pass[12] = '\0';
    char ssid[27];
    snprintf(ssid, sizeof(ssid), "NW-OS-%04X",
             (unsigned)(ESP.getEfuseMac() & 0xFFFF));
    char cap[30];
    snprintf(cap, sizeof(cap), "MAX APP: %lu KB",
             (unsigned long)(slot->size / 1024UL));
    display.epd2.setBusyCallback(nullptr);
    statusScreen(ssid, pass, cap);
    WiFiManager manager;
    manager.setTitle("NeuroWatch OTA");
    manager.setShowInfoErase(false);
    manager.setShowInfoUpdate(true);
    manager.setConfigPortalTimeout(NW_OTA_TIMEOUT_SECONDS);
    manager.startConfigPortal(ssid, pass);
    WiFi.mode(WIFI_OFF);
    btStop();
    display.epd2.setBusyCallback(displayBusyCallback);
    RTC.read(currentTime);
    showWatchFace(false);
  }
};

NeuroWatch watch(nwSettings);
void setup() {
  if (retainedFace > 2) {
    Preferences prefs;
    if (prefs.begin("nw-os", true)) {
      retainedFace = prefs.getUChar("face", NW_FACE);
      prefs.end();
    } else {
      retainedFace = NW_FACE;
    }
  }
  watch.setFace(retainedFace);
  watch.init();
}
void loop() {} // Watchy goes to deep sleep after handling RTC/button wakeup.
