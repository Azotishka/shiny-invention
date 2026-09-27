#include <Arduino.h>
#include <Watchy.h>
#include <Preferences.h>
#include <WiFi.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <U8g2_for_Adafruit_GFX.h>
#include <string>
#include "alarm_policy.h"
#include "neuro_config.h"
#include "time_sync_packet.h"

// NeuroWatch OS v0.9 - phone time sync and clearer alarm controls.
// Target: Watchy V2 / ESP32-PICO-D4.

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

extern bool alreadyInMenu;

static constexpr uint32_t NW_PREF_MAGIC = 0x4E573130UL; // "NW10"; loads migrated preferences.
RTC_DATA_ATTR uint32_t nwPrefMagic = 0;
RTC_DATA_ATTR uint8_t nwUse24h = NW_DEFAULT_24H;
RTC_DATA_ATTR uint8_t nwDateDmy = NW_DEFAULT_DMY;
RTC_DATA_ATTR uint8_t nwVibration = NW_DEFAULT_VIBRATION;
RTC_DATA_ATTR uint8_t nwHourlyBuzz = NW_DEFAULT_HOURLY_BUZZ;
RTC_DATA_ATTR uint8_t nwAlarmEnabled = NW_DEFAULT_ALARM_ENABLED;
RTC_DATA_ATTR uint8_t nwAlarmVibration = NW_DEFAULT_ALARM_VIBRATION;
RTC_DATA_ATTR uint8_t nwRussianUi = 1;
RTC_DATA_ATTR uint8_t nwDarkTheme = 0;
RTC_DATA_ATTR uint8_t nwAlarmHour = NW_DEFAULT_ALARM_HOUR;
RTC_DATA_ATTR uint8_t nwAlarmMinute = NW_DEFAULT_ALARM_MINUTE;
RTC_DATA_ATTR int16_t nwUtcOffsetMinutes = NW_DEFAULT_TIMEZONE_MINUTES;
RTC_DATA_ATTR uint32_t nwStepGoal = NW_STEP_GOAL;
RTC_DATA_ATTR uint16_t nwBestReactionMs = 0;
RTC_DATA_ATTR uint32_t nwAlarmLastDay = 0xFFFFFFFFUL;
RTC_DATA_ATTR uint8_t nwMenuPartial = 0;
RTC_DATA_ATTR uint8_t nwEditorPartial = 0;
RTC_DATA_ATTR uint8_t nwAppReturnToMenu = 0;
RTC_DATA_ATTR uint32_t nwLastBuzzStamp = 0xFFFFFFFFUL;

static U8G2_FOR_ADAFRUIT_GFX nwTextRenderer;

static const char *nwText(const char *english, const char *russian) {
  return nwRussianUi ? russian : english;
}

static portMUX_TYPE nwPhoneSyncMux = portMUX_INITIALIZER_UNLOCKED;
static NwLocalTimeSync nwPendingPhoneTime = {};
static volatile bool nwHasPendingPhoneTime = false;
static volatile bool nwInvalidPhonePacket = false;
static BLECharacteristic *nwTimeSyncStatusCharacteristic = nullptr;

static void loadUserPrefs() {
  if (nwPrefMagic == NW_PREF_MAGIC) return;

  Preferences prefs;
  if (prefs.begin("nw-os", true)) {
    nwUse24h = prefs.getBool("24h", NW_DEFAULT_24H);
    nwDateDmy = prefs.getBool("dmy", NW_DEFAULT_DMY);
    nwVibration = prefs.getBool("vib", NW_DEFAULT_VIBRATION);
    nwHourlyBuzz = prefs.getBool("hourbuzz", NW_DEFAULT_HOURLY_BUZZ);
    nwAlarmEnabled = prefs.getBool("alarm_on", NW_DEFAULT_ALARM_ENABLED);
    nwAlarmVibration = prefs.getBool("alarm_vib", NW_DEFAULT_ALARM_VIBRATION);
    nwRussianUi = prefs.getBool("lang_ru", true);
    nwDarkTheme = prefs.getBool("dark", false);
    nwAlarmHour = prefs.getUChar("alarm_h", NW_DEFAULT_ALARM_HOUR);
    nwAlarmMinute = prefs.getUChar("alarm_m", NW_DEFAULT_ALARM_MINUTE);
    nwUtcOffsetMinutes = prefs.getShort("tz_min", NW_DEFAULT_TIMEZONE_MINUTES);
    nwStepGoal = prefs.getUInt("step_goal", NW_STEP_GOAL);
    nwBestReactionMs = prefs.getUShort("rx_best", 0);
    prefs.end();
  } else {
    nwUse24h = NW_DEFAULT_24H;
    nwDateDmy = NW_DEFAULT_DMY;
    nwVibration = NW_DEFAULT_VIBRATION;
    nwHourlyBuzz = NW_DEFAULT_HOURLY_BUZZ;
    nwAlarmEnabled = NW_DEFAULT_ALARM_ENABLED;
    nwAlarmVibration = NW_DEFAULT_ALARM_VIBRATION;
    nwRussianUi = true;
    nwDarkTheme = false;
    nwAlarmHour = NW_DEFAULT_ALARM_HOUR;
    nwAlarmMinute = NW_DEFAULT_ALARM_MINUTE;
    nwUtcOffsetMinutes = NW_DEFAULT_TIMEZONE_MINUTES;
    nwStepGoal = NW_STEP_GOAL;
    nwBestReactionMs = 0;
  }
  if (nwAlarmHour > 23) nwAlarmHour = NW_DEFAULT_ALARM_HOUR;
  if (nwAlarmMinute > 59) nwAlarmMinute = NW_DEFAULT_ALARM_MINUTE;
  if (nwUtcOffsetMinutes < -720 || nwUtcOffsetMinutes > 840)
    nwUtcOffsetMinutes = NW_DEFAULT_TIMEZONE_MINUTES;
  if (nwStepGoal < NW_STEP_GOAL_MIN || nwStepGoal > NW_STEP_GOAL_MAX)
    nwStepGoal = NW_STEP_GOAL;
  nwPrefMagic = NW_PREF_MAGIC;
}

static void saveBoolPref(const char *key, bool value) {
  Preferences prefs;
  if (prefs.begin("nw-os", false)) {
    prefs.putBool(key, value);
    prefs.end();
  }
}

static void saveBytePref(const char *key, uint8_t value) {
  Preferences prefs;
  if (prefs.begin("nw-os", false)) {
    prefs.putUChar(key, value);
    prefs.end();
  }
}

static void saveUIntPref(const char *key, uint32_t value) {
  Preferences prefs;
  if (prefs.begin("nw-os", false)) {
    prefs.putUInt(key, value);
    prefs.end();
  }
}

static void saveUShortPref(const char *key, uint16_t value) {
  Preferences prefs;
  if (prefs.begin("nw-os", false)) {
    prefs.putUShort(key, value);
    prefs.end();
  }
}

static bool saveShortPref(const char *key, int16_t value) {
  Preferences prefs;
  if (!prefs.begin("nw-os", false)) return false;
  const bool saved = prefs.putShort(key, value) == sizeof(value);
  prefs.end();
  return saved;
}

class NwTimeSyncWriteCallbacks : public BLECharacteristicCallbacks {
 public:
  void onWrite(BLECharacteristic *characteristic) override {
    const std::string value = characteristic->getValue();
    NwLocalTimeSync decoded = {};
    const bool valid = nwDecodeTimeSyncPacket(
        reinterpret_cast<const uint8_t *>(value.data()), value.size(), decoded);

    portENTER_CRITICAL(&nwPhoneSyncMux);
    if (valid) {
      nwPendingPhoneTime = decoded;
      nwHasPendingPhoneTime = true;
    } else {
      nwInvalidPhonePacket = true;
    }
    portEXIT_CRITICAL(&nwPhoneSyncMux);
  }
};

class NeuroWatch : public Watchy {
 public:
  using Watchy::Watchy;

  void drawWatchFace() override {
    if (!maybeDailyAlarm()) maybeHourlyBuzz();

    display.setFullWindow();
    display.fillScreen(backgroundColor());
    display.setTextColor(foregroundColor());
    display.setTextWrap(false);

    drawStandardWallpaper();

    const uint8_t rawHour = currentTime.Hour % 24;
    uint8_t shownHour = rawHour;
    bool pm = false;
    if (!nwUse24h) {
      pm = rawHour >= 12;
      shownHour = rawHour % 12;
      if (shownHour == 0) shownHour = 12;
    }

    digit(20, 37, shownHour / 10);
    digit(55, 37, shownHour % 10);
    display.fillRect(93, 49, 4, 4, foregroundColor());
    display.fillRect(93, 63, 4, 4, foregroundColor());
    digit(106, 37, currentTime.Minute / 10);
    digit(141, 37, currentTime.Minute % 10);

    char buf[40];
    const char *wd = weekdayName();
    if (nwDateDmy) {
      snprintf(buf, sizeof(buf), "%s  %02u.%02u.%04d",
               wd,
               (unsigned)currentTime.Day,
               (unsigned)currentTime.Month,
               tmYearToCalendar(currentTime.Year));
    } else {
      snprintf(buf, sizeof(buf), "%s  %02u/%02u/%04d",
               wd,
               (unsigned)currentTime.Month,
               (unsigned)currentTime.Day,
               tmYearToCalendar(currentTime.Year));
    }
    display.fillRect(8, 85, 184, 17, foregroundColor());
    drawTextColor(12, 90, buf, backgroundColor());

    if (!nwUse24h) {
      label(171, 29, nwText(pm ? "PM" : "AM", pm ? "ПП" : "ДП"));
    } else {
      label(171, 29, "24");
    }

    drawBatteryWidget(10, 111);
    drawStepsWidget(10, 137);

    if (nwAlarmEnabled) {
      char alarm[32];
      snprintf(alarm, sizeof(alarm), nwText("ALARM %02u:%02u", "БУД %02u:%02u"),
               (unsigned)nwAlarmHour, (unsigned)nwAlarmMinute);
      label(10, 153, alarm);
    } else {
      label(10, 153, nwText("ALARM OFF", "БУДИЛЬНИК ВЫКЛ"));
    }
    char zone[16];
    formatUtcOffset(zone, sizeof(zone));
    label(132, 153, zone);

    display.drawLine(8, 169, 191, 169, foregroundColor());
    label(10, 176, nwText("UP:STEPS  DN:STATUS", "ВВЕРХ: ШАГИ  ВНИЗ: СТАТУС"));
    label(10, 188, nwText("MENU:SETTINGS   NW " NW_VERSION,
                           "МЕНЮ:НАСТРОЙКИ   NW " NW_VERSION));
  }

  void handleButtonPress() override {
    const uint64_t pressed = esp_sleep_get_ext1_wakeup_status();

    if (guiState == WATCHFACE_STATE) {
      if (pressed & MENU_BTN_MASK) {
        menuIndex = 0;
        showNeuroMenu(false);
      } else if (pressed & UP_BTN_MASK) {
        nwAppReturnToMenu = 0;
        showStepsCard();
      } else if (pressed & DOWN_BTN_MASK) {
        nwAppReturnToMenu = 0;
        showDiagnostics();
      } else if (pressed & BACK_BTN_MASK) {
        nwAppReturnToMenu = 0;
        showAbout();
      }
    } else if (guiState == MAIN_MENU_STATE) {
      if (pressed & BACK_BTN_MASK) {
        RTC.read(currentTime);
        showWatchFace(false);
      } else if (pressed & UP_BTN_MASK) {
        menuIndex = (menuIndex + MENU_COUNT - 1) % MENU_COUNT;
        showNeuroMenu(true);
      } else if (pressed & DOWN_BTN_MASK) {
        menuIndex = (menuIndex + 1) % MENU_COUNT;
        showNeuroMenu(true);
      } else if (pressed & MENU_BTN_MASK) {
        selectMenuItem();
      }
    } else {
      if (nwAppReturnToMenu) {
        showNeuroMenu(false);
      } else {
        RTC.read(currentTime);
        showWatchFace(false);
      }
    }

    waitAllReleased(2500);
  }

 private:
  uint16_t foregroundColor() const {
    return nwDarkTheme ? GxEPD_WHITE : GxEPD_BLACK;
  }

  uint16_t backgroundColor() const {
    return nwDarkTheme ? GxEPD_BLACK : GxEPD_WHITE;
  }

  static constexpr int MENU_COUNT = 19;

  void drawStandardWallpaper() {
    display.drawRect(2, 2, 196, 196, foregroundColor());
    display.fillRect(7, 6, 186, 19, foregroundColor());
    drawTextColor(10, 11, nwText("NEUROWATCH // DAILY", "НЕЙРОЧАСЫ // ДЕНЬ"), backgroundColor());
    drawTextColor(159, 11, "OS " NW_VERSION, backgroundColor());

    // One built-in standard wallpaper: light technical corner marks.
    display.drawLine(8, 31, 27, 31, foregroundColor());
    display.drawLine(8, 31, 8, 50, foregroundColor());
    display.drawLine(191, 31, 172, 31, foregroundColor());
    display.drawLine(191, 31, 191, 50, foregroundColor());
    display.drawLine(8, 164, 27, 164, foregroundColor());
    display.drawLine(8, 164, 8, 153, foregroundColor());
    display.drawLine(191, 164, 172, 164, foregroundColor());
    display.drawLine(191, 164, 191, 153, foregroundColor());
  }

  void label(int x, int y, const char *s) {
    drawTextColor(x, y, s, foregroundColor());
  }

  void drawTextColor(int x, int y, const char *s, uint16_t color) {
    display.setFont(nullptr);
    display.setTextSize(1);
    display.setTextColor(color);
    if (nwRussianUi) {
      nwTextRenderer.setFontMode(1);
      nwTextRenderer.setFontDirection(0);
      nwTextRenderer.setForegroundColor(color);
      nwTextRenderer.setFont(u8g2_font_5x8_t_cyrillic);
      nwTextRenderer.setCursor(x, y + 7);
      nwTextRenderer.print(s);
      nwTextRenderer.setCursor(x + 1, y + 7);
      nwTextRenderer.print(s);
    } else {
      display.setCursor(x, y);
      display.print(s);
      display.setCursor(x + 1, y);
      display.print(s);
    }
  }

  const char *weekdayName() {
    static const char *const english[] = {
        "SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"};
    static const char *const russian[] = {
        "ВС", "ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ"};
    tmElements_t copy = currentTime;
    const uint8_t day = weekday(makeTime(copy));
    if (day < 1 || day > 7) return "---";
    return nwText(english[day - 1], russian[day - 1]);
  }

  void digit(int x, int y, uint8_t value) {
    static const uint8_t segments[10] = {
        0x3f, 0x06, 0x5b, 0x4f, 0x66,
        0x6d, 0x7d, 0x07, 0x7f, 0x6f};
    const uint8_t bits = segments[value % 10];
    constexpr int w = 29, h = 38, t = 5, mid = h / 2;
    if (bits & 0x01) display.fillRect(x + t, y, w - 2 * t, t, foregroundColor());
    if (bits & 0x02) display.fillRect(x + w - t, y + t, t, mid - t, foregroundColor());
    if (bits & 0x04) display.fillRect(x + w - t, y + mid, t, mid - t, foregroundColor());
    if (bits & 0x08) display.fillRect(x + t, y + h - t, w - 2 * t, t, foregroundColor());
    if (bits & 0x10) display.fillRect(x, y + mid, t, mid - t, foregroundColor());
    if (bits & 0x20) display.fillRect(x, y + t, t, mid - t, foregroundColor());
    if (bits & 0x40) display.fillRect(x + t, y + mid - t / 2, w - 2 * t, t, foregroundColor());
  }

  void formatUtcOffset(char *buf, size_t size) {
    int offset = nwUtcOffsetMinutes;
    const char sign = offset < 0 ? '-' : '+';
    if (offset < 0) offset = -offset;
    snprintf(buf, size, "UTC%c%02d:%02d", sign, offset / 60, offset % 60);
  }

  int batteryPercent(float voltage) {
    if (!(voltage > 0.0f && voltage < 6.0f)) return -1;
    if (voltage >= 4.18f) return 100;
    if (voltage <= 3.45f) return 0;
    int pct = (int)(((voltage - 3.45f) * 100.0f) / 0.73f + 0.5f);
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    return pct;
  }

  void drawBatteryWidget(int x, int y) {
    const float voltage = getBatteryVoltage();
    const int pct = batteryPercent(voltage);

    char buf[32];
    if (pct < 0) {
      snprintf(buf, sizeof(buf), "%s", nwText("BAT --%", "АКБ --%"));
    } else {
      snprintf(buf, sizeof(buf), nwText("BAT %3d%%", "АКБ %3d%%"), pct);
    }
    label(x, y, buf);

    display.drawRect(72, y - 2, 82, 10, foregroundColor());
    display.fillRect(154, y + 1, 3, 4, foregroundColor());
    if (pct > 0) {
      const int fill = (pct * 78) / 100;
      display.fillRect(74, y, fill, 6, foregroundColor());
    }

    if (voltage > 0.0f && voltage < 6.0f) {
      const unsigned cv = (unsigned)(voltage * 100.0f + 0.5f);
      snprintf(buf, sizeof(buf), "%u.%02uV", cv / 100, cv % 100);
      label(163, y, buf);
    }
  }

  void drawStepsWidget(int x, int y) {
    const uint32_t steps = sensor.getCounter();
    char buf[32];
    snprintf(buf, sizeof(buf), nwText("STEPS %lu", "ШАГИ %lu"), (unsigned long)steps);
    label(x, y, buf);

    const uint32_t capped = steps > nwStepGoal ? nwStepGoal : steps;
    display.drawRect(82, y - 2, 109, 10, foregroundColor());
    const int fill = (int)((capped * 105UL) / nwStepGoal);
    if (fill > 0) display.fillRect(84, y, fill, 6, foregroundColor());
  }

  void maybeHourlyBuzz() {
    if (!nwHourlyBuzz || currentTime.Minute != 0) return;
    const uint32_t stamp =
        (uint32_t)currentTime.Month * 10000UL +
        (uint32_t)currentTime.Day * 100UL +
        (uint32_t)currentTime.Hour;
    if (stamp == nwLastBuzzStamp) return;
    nwLastBuzzStamp = stamp;
    vibMotor(75, 4);
  }

  void playAlarmVibration() {
    // Watchy's second argument is the number of on/off toggles, not intensity.
    // Two full-length patterns give the motor time to spin up and are easy to feel.
    vibMotor(100, 20);
    delay(250);
    vibMotor(100, 20);
  }

  void testVibration() {
    playAlarmVibration();
  }

  void drawGameFrame(const char *title, const char *line1,
                     const char *line2, const char *line3) {
    display.setFullWindow();
    display.fillScreen(backgroundColor());
    display.setTextColor(foregroundColor());
    display.drawRect(2, 2, 196, 196, foregroundColor());
    label(10, 12, title);
    display.drawLine(8, 28, 191, 28, foregroundColor());
    label(12, 54, line1);
    label(12, 82, line2);
    label(12, 110, line3);
    label(12, 181, nwText("MENU: SELECT   BACK: EXIT", "МЕНЮ: ВЫБОР   НАЗАД: ВЫХОД"));
  }

  int waitGameButton(uint32_t timeoutMs) {
    const uint32_t started = millis();
    while ((uint32_t)(millis() - started) < timeoutMs) {
      if (digitalRead(MENU_BTN_PIN)) {
        waitAllReleased(1200);
        return 1;
      }
      if (digitalRead(BACK_BTN_PIN)) {
        waitAllReleased(1200);
        return 4;
      }
      delay(20);
    }
    return 0;
  }

  void drawDiceFace(uint8_t face) {
    display.drawRoundRect(53, 40, 94, 96, 12, foregroundColor());
    const int8_t x[] = {76, 100, 124};
    const int8_t y[] = {63, 88, 113};
    const uint16_t pips[] = {
        1U << 4,
        (1U << 0) | (1U << 8),
        (1U << 0) | (1U << 4) | (1U << 8),
        (1U << 0) | (1U << 2) | (1U << 6) | (1U << 8),
        (1U << 0) | (1U << 2) | (1U << 4) | (1U << 6) | (1U << 8),
        (1U << 0) | (1U << 2) | (1U << 3) | (1U << 5) | (1U << 6) | (1U << 8),
    };
    const uint16_t pattern = pips[(face - 1) % 6];
    for (uint8_t row = 0; row < 3; ++row) {
      for (uint8_t col = 0; col < 3; ++col) {
        const uint8_t bit = row * 3 + col;
        if (pattern & (1U << bit))
          display.fillCircle(x[col], y[row], 5, foregroundColor());
      }
    }
  }

  void playDiceGame() {
    guiState = APP_STATE;
    nwAppReturnToMenu = 1;
    waitAllReleased(1200);
    uint8_t face = (uint8_t)(esp_random() % 6U) + 1;
    while (true) {
      display.fillScreen(backgroundColor());
      display.setTextColor(foregroundColor());
      display.drawRect(2, 2, 196, 196, foregroundColor());
      label(10, 12, nwText("DICE", "КУБИК"));
      display.drawLine(8, 28, 191, 28, foregroundColor());
      drawDiceFace(face);
      label(12, 151, nwText("MENU: ROLL AGAIN", "МЕНЮ: БРОСИТЬ ЕЩЁ"));
      label(12, 174, nwText("BACK: EXIT", "НАЗАД: ВЫХОД"));
      display.display(false);

      const int button = waitGameButton(60000UL);
      if (button != 1) break;
      face = (uint8_t)(esp_random() % 6U) + 1;
      buzzConfirm();
    }
    showNeuroMenu(false);
  }

  void playReactionGame() {
    guiState = APP_STATE;
    nwAppReturnToMenu = 1;
    waitAllReleased(1200);
    bool replay = true;
    while (replay) {
      drawGameFrame(nwText("REACTION TEST", "ТЕСТ РЕАКЦИИ"),
                    nwText("Press MENU to start", "НАЖМИ МЕНЮ ДЛЯ СТАРТА"),
                    nwText("Wait for GO, then press", "ЖДИ СИГНАЛА, ПОТОМ ЖМИ"),
                    nwText("Keep your finger off MENU", "НЕ НАЖИМАЙ РАНЬШЕ СИГНАЛА"));
      display.display(false);
      const int startButton = waitGameButton(60000UL);
      if (startButton != 1) break;

      const uint32_t waitMs = 1500UL + (esp_random() % 3500UL);
      drawGameFrame(nwText("REACTION TEST", "ТЕСТ РЕАКЦИИ"),
                    nwText("Wait for the signal...", "ЖДИ СИГНАЛА..."),
                    nwText("Do not press yet", "ПОКА НЕ НАЖИМАЙ"),
                    nwText("BACK: CANCEL", "НАЗАД: ОТМЕНА"));
      display.display(false);
      const uint32_t waitStarted = millis();
      bool falseStart = false;
      bool cancelled = false;
      while ((uint32_t)(millis() - waitStarted) < waitMs) {
        if (digitalRead(BACK_BTN_PIN)) {
          waitAllReleased(1200);
          cancelled = true;
          break;
        }
        if (digitalRead(MENU_BTN_PIN)) {
          waitAllReleased(1200);
          falseStart = true;
          break;
        }
        delay(10);
      }
      if (cancelled) break;

      if (falseStart) {
        drawGameFrame(nwText("TOO EARLY!", "СЛИШКОМ РАНО!"),
                      nwText("Wait until GO appears", "ДОЖДИСЬ СИГНАЛА"),
                      nwText("Try again", "ПОПРОБУЙ ЕЩЁ РАЗ"), "");
        display.display(false);
      } else {
        drawGameFrame(nwText("GO!", "ЖМИ!"),
                      nwText("Press MENU now", "НАЖМИ МЕНЮ СЕЙЧАС"), "", "");
        display.display(false);
        const uint32_t signalAt = millis();
        bool answered = false;
        uint32_t elapsed = 0;
        while ((uint32_t)(millis() - signalAt) < 10000UL) {
          if (digitalRead(BACK_BTN_PIN)) {
            waitAllReleased(1200);
            cancelled = true;
            break;
          }
          if (digitalRead(MENU_BTN_PIN)) {
            elapsed = millis() - signalAt;
            waitAllReleased(1200);
            answered = true;
            break;
          }
          delay(5);
        }
        if (cancelled) break;

        char result[24];
        char best[28];
        if (answered) {
          snprintf(result, sizeof(result), nwText("%lu ms", "%lu мс"),
                   (unsigned long)elapsed);
          if (nwBestReactionMs == 0 || elapsed < nwBestReactionMs) {
            nwBestReactionMs = (uint16_t)elapsed;
            saveUShortPref("rx_best", nwBestReactionMs);
          }
          snprintf(best, sizeof(best), nwText("BEST: %u ms", "РЕКОРД: %u мс"),
                   (unsigned)nwBestReactionMs);
          drawGameFrame(nwText("YOUR TIME", "ТВОЁ ВРЕМЯ"), result, best,
                        nwText("Lower is better", "МЕНЬШЕ — БЫСТРЕЕ"));
          buzzConfirm();
        } else {
          drawGameFrame(nwText("TIME IS UP", "ВРЕМЯ ВЫШЛО"),
                        nwText("Try again", "ПОПРОБУЙ ЕЩЁ РАЗ"), "", "");
        }
        display.display(false);
      }

      const int next = waitGameButton(60000UL);
      replay = next == 1;
    }
    showNeuroMenu(false);
  }

  bool maybeDailyAlarm() {
    const uint32_t year = (uint32_t)tmYearToCalendar(currentTime.Year);
    const uint32_t dayStamp = ((year * 13UL + currentTime.Month) * 32UL) +
                              currentTime.Day;
    const bool triggered = nwShouldFireDailyAlarm(
        nwAlarmEnabled, currentTime.Hour, currentTime.Minute,
        nwAlarmHour, nwAlarmMinute, dayStamp, nwAlarmLastDay);
    if (nwShouldVibrateAlarm(triggered, nwAlarmVibration))
      playAlarmVibration();
    return triggered;
  }

  void buzzConfirm() {
    if (nwVibration) vibMotor(75, 4);
  }

  void menuLabel(int item, char *buf, size_t size) {
    switch (item) {
      case 0: snprintf(buf, size, "%s", nwText("SET TIME", "НАСТРОИТЬ ВРЕМЯ")); break;
      case 1: snprintf(buf, size, "%s", nwText("SET DATE", "НАСТРОИТЬ ДАТУ")); break;
      case 2:
        snprintf(buf, size, nwText("24H MODE: %s", "24Ч ФОРМАТ: %s"),
                 nwText(nwUse24h ? "ON" : "OFF", nwUse24h ? "ВКЛ" : "ВЫКЛ"));
        break;
      case 3:
        snprintf(buf, size, nwText("DATE FORMAT: %s", "ФОРМАТ ДАТЫ: %s"),
                 nwDateDmy ? "DD.MM" : "MM/DD");
        break;
      case 4:
        snprintf(buf, size, nwText("BUTTON VIB: %s", "ВИБРОКНОПКИ: %s"),
                 nwText(nwVibration ? "ON" : "OFF", nwVibration ? "ВКЛ" : "ВЫКЛ"));
        break;
      case 5:
        snprintf(buf, size, nwText("HOURLY BUZZ: %s", "СИГНАЛ ЧАСА: %s"),
                 nwText(nwHourlyBuzz ? "ON" : "OFF", nwHourlyBuzz ? "ВКЛ" : "ВЫКЛ"));
        break;
      case 6:
        snprintf(buf, size, nwText("DAILY ALARM: %s", "БУДИЛЬНИК: %s"),
                 nwText(nwAlarmEnabled ? "ON" : "OFF", nwAlarmEnabled ? "ВКЛ" : "ВЫКЛ"));
        break;
      case 7:
        snprintf(buf, size, nwText("ALARM TIME %02u:%02u", "БУДИЛЬНИК %02u:%02u"),
                 (unsigned)nwAlarmHour, (unsigned)nwAlarmMinute);
        break;
      case 8:
        snprintf(buf, size, nwText("ALARM VIB: %s", "ВИБРОБУДИЛЬНИК: %s"),
                 nwText(nwAlarmVibration ? "ON" : "OFF", nwAlarmVibration ? "ВКЛ" : "ВЫКЛ"));
        break;
      case 9: snprintf(buf, size, "%s", nwText("TEST VIBRATION", "ПРОВЕРИТЬ ВИБРАЦИЮ")); break;
      case 10: snprintf(buf, size, "%s", nwText("SYNC PHONE TIME", "СИНХРОН. С ТЕЛЕФОНОМ")); break;
      case 11:
        snprintf(buf, size, nwText("STEP GOAL: %lu", "ЦЕЛЬ ШАГОВ: %lu"),
                 (unsigned long)nwStepGoal);
        break;
      case 12: snprintf(buf, size, "%s", nwText("RESET STEPS", "СБРОСИТЬ ШАГИ")); break;
      case 13: snprintf(buf, size, "%s", nwText("DIAGNOSTICS", "СВЕДЕНИЯ О ЧАСАХ")); break;
      case 14: snprintf(buf, size, "%s", nwText("ABOUT / UPDATE", "О ЧАСАХ / ОБНОВЛЕНИЕ")); break;
      case 15: snprintf(buf, size, "%s", nwText("LANGUAGE: ENGLISH", "ЯЗЫК: РУССКИЙ")); break;
      case 16:
        snprintf(buf, size, nwText("DARK THEME: %s", "ТЁМНАЯ ТЕМА: %s"),
                 nwText(nwDarkTheme ? "ON" : "OFF", nwDarkTheme ? "ВКЛ" : "ВЫКЛ"));
        break;
      case 17: snprintf(buf, size, "%s", nwText("GAME: DICE", "ИГРА: КУБИК")); break;
      default: snprintf(buf, size, "%s", nwText("GAME: REACTION", "ИГРА: РЕАКЦИЯ")); break;
    }
  }

  void showNeuroMenu(bool requestPartial) {
    display.setFullWindow();
    display.fillScreen(backgroundColor());
    display.setTextColor(foregroundColor());
    display.setTextWrap(false);

    display.fillRect(5, 5, 190, 21, foregroundColor());
    drawTextColor(9, 12, nwText("NW://SETTINGS", "NW://НАСТРОЙКИ"), backgroundColor());
    char page[12];
    snprintf(page, sizeof(page), "%02d/%02d", menuIndex + 1, MENU_COUNT);
    drawTextColor(158, 12, page, backgroundColor());

    int top = menuIndex - 2;
    if (top < 0) top = 0;
    const int maxTop = MENU_COUNT - NW_MENU_VISIBLE_ROWS;
    if (top > maxTop) top = maxTop;

    // Russian strings use UTF-8 and take more bytes than their visible width.
    char buf[72];
    for (int row = 0; row < NW_MENU_VISIBLE_ROWS; ++row) {
      const int item = top + row;
      const int y = 32 + row * 28;
      menuLabel(item, buf, sizeof(buf));
      if (item == menuIndex) {
        display.fillRect(5, y - 4, 190, 21, foregroundColor());
      display.setTextColor(backgroundColor());
    } else {
      display.setTextColor(foregroundColor());
    }
      drawTextColor(10, y, buf, item == menuIndex ? backgroundColor() : foregroundColor());
    }

    display.setTextColor(foregroundColor());
    display.drawLine(5, 176, 194, 176, foregroundColor());
    label(7, 184, nwText("UP/DN MOVE  M:OK  B:BACK",
                          "ВВЕРХ/ВНИЗ: ВЫБОР  М:ОК  НАЗАД"));

    const bool partial = requestPartial && nwMenuPartial < 8;
    nwMenuPartial = partial ? nwMenuPartial + 1 : 0;
    display.display(partial);

    guiState = MAIN_MENU_STATE;
    alreadyInMenu = false;
  }

  void selectMenuItem() {
    switch (menuIndex) {
      case 0:
        editTime(false);
        return;
      case 1:
        editDate();
        return;
      case 2:
        nwUse24h = !nwUse24h;
        saveBoolPref("24h", nwUse24h);
        buzzConfirm();
        showNeuroMenu(true);
        return;
      case 3:
        nwDateDmy = !nwDateDmy;
        saveBoolPref("dmy", nwDateDmy);
        buzzConfirm();
        showNeuroMenu(true);
        return;
      case 4:
        nwVibration = !nwVibration;
        saveBoolPref("vib", nwVibration);
        buzzConfirm();
        showNeuroMenu(true);
        return;
      case 5:
        nwHourlyBuzz = !nwHourlyBuzz;
        saveBoolPref("hourbuzz", nwHourlyBuzz);
        buzzConfirm();
        showNeuroMenu(true);
        return;
      case 6:
        nwAlarmEnabled = !nwAlarmEnabled;
        saveBoolPref("alarm_on", nwAlarmEnabled);
        buzzConfirm();
        showNeuroMenu(true);
        return;
      case 7:
        editTime(true);
        return;
      case 8:
        nwAlarmVibration = !nwAlarmVibration;
        saveBoolPref("alarm_vib", nwAlarmVibration);
        buzzConfirm();
        showNeuroMenu(true);
        return;
      case 9:
        testVibration();
        showNeuroMenu(true);
        return;
      case 10:
        syncPhoneTime();
        return;
      case 11:
        editStepGoal();
        return;
      case 12:
        resetSteps();
        return;
      case 13:
        nwAppReturnToMenu = 1;
        showDiagnostics();
        return;
      case 14:
        nwAppReturnToMenu = 1;
        showAbout();
        return;
      case 15:
        nwRussianUi = !nwRussianUi;
        saveBoolPref("lang_ru", nwRussianUi);
        showNeuroMenu(false);
        return;
      case 16:
        nwDarkTheme = !nwDarkTheme;
        saveBoolPref("dark", nwDarkTheme);
        showNeuroMenu(false);
        return;
      case 17:
        playDiceGame();
        return;
      case 18:
        playReactionGame();
        return;
    }
  }

  void showPhoneSyncState(const char *title, const char *line1, const char *line2) {
    display.setFullWindow();
    display.fillScreen(backgroundColor());
    display.setTextColor(foregroundColor());
    display.drawRect(2, 2, 196, 196, foregroundColor());
    label(10, 12, nwText("NW://PHONE SYNC", "NW://СИНХРОНИЗАЦИЯ"));
    display.drawLine(8, 27, 191, 27, foregroundColor());
    label(10, 55, title);
    label(10, 85, line1);
    label(10, 105, line2);
    display.drawLine(8, 169, 191, 169, foregroundColor());
    label(10, 181, nwText("BACK: CANCEL / RETURN", "НАЗАД: ОТМЕНА / ВЫХОД"));
    display.display(false);
  }

  void setPhoneSyncStatus(const char *status) {
    if (!nwTimeSyncStatusCharacteristic) return;
    nwTimeSyncStatusCharacteristic->setValue(status);
    nwTimeSyncStatusCharacteristic->notify();
  }

  void syncPhoneTime() {
    guiState = APP_STATE;
    nwAppReturnToMenu = 1;
    waitAllReleased(1500);

    portENTER_CRITICAL(&nwPhoneSyncMux);
    nwHasPendingPhoneTime = false;
    nwInvalidPhonePacket = false;
    portEXIT_CRITICAL(&nwPhoneSyncMux);

    showPhoneSyncState(
        nwText("WAITING FOR PHONE", "ЖДУ ТЕЛЕФОН"),
        nwText("Open NeuroWatch Connect", "ОТКРОЙ NEUROWATCH CONNECT"),
        nwText("Tap SYNC on your phone", "НАЖМИ СИНХРОНИЗАЦИЮ В ПРИЛОЖЕНИИ"));

    BLEDevice::init("NeuroWatch");
    BLEServer *server = BLEDevice::createServer();
    BLEService *service = server->createService(NW_BLE_SERVICE_UUID);
    BLECharacteristic *timeCharacteristic = service->createCharacteristic(
        NW_BLE_TIME_UUID,
        BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
    nwTimeSyncStatusCharacteristic = service->createCharacteristic(
        NW_BLE_STATUS_UUID,
        BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
    nwTimeSyncStatusCharacteristic->addDescriptor(new BLE2902());
    nwTimeSyncStatusCharacteristic->setValue("READY");
    timeCharacteristic->setCallbacks(new NwTimeSyncWriteCallbacks());
    service->start();

    BLEAdvertising *advertising = BLEDevice::getAdvertising();
    advertising->addServiceUUID(NW_BLE_SERVICE_UUID);
    advertising->setScanResponse(true);
    advertising->start();

    const uint32_t startedAt = millis();
    bool synced = false;
    bool cancelled = false;
    while ((uint32_t)(millis() - startedAt) < NW_BLE_SYNC_TIMEOUT_MS) {
      if (digitalRead(BACK_BTN_PIN)) {
        cancelled = true;
        break;
      }
      NwLocalTimeSync incoming = {};
      bool received = false;
      bool invalid = false;
      portENTER_CRITICAL(&nwPhoneSyncMux);
      if (nwHasPendingPhoneTime) {
        incoming = nwPendingPhoneTime;
        nwHasPendingPhoneTime = false;
        received = true;
      }
      if (nwInvalidPhonePacket) {
        nwInvalidPhonePacket = false;
        invalid = true;
      }
      portEXIT_CRITICAL(&nwPhoneSyncMux);

      if (invalid) setPhoneSyncStatus("INVALID");
      if (received) {
        tmElements_t syncedTime = {};
        syncedTime.Year = y2kYearToTm(incoming.year - 2000);
        syncedTime.Month = incoming.month;
        syncedTime.Day = incoming.day;
        syncedTime.Hour = incoming.hour;
        syncedTime.Minute = incoming.minute;
        syncedTime.Second = incoming.second;

        const bool offsetSaved = saveShortPref("tz_min", incoming.utcOffsetMinutes);
        nwUtcOffsetMinutes = incoming.utcOffsetMinutes;
        RTC.set(syncedTime);

        tmElements_t readBack = {};
        RTC.read(readBack);
        const bool clockVerified =
            tmYearToCalendar(readBack.Year) == incoming.year &&
            readBack.Month == incoming.month && readBack.Day == incoming.day &&
            readBack.Hour == incoming.hour && readBack.Minute == incoming.minute &&
            readBack.Second == incoming.second;
        if (offsetSaved && clockVerified) {
          setPhoneSyncStatus("OK");
          char zone[16];
          formatUtcOffset(zone, sizeof(zone));
          showPhoneSyncState(nwText("TIME UPDATED", "ВРЕМЯ ОБНОВЛЕНО"),
                             nwText("Phone date and time saved", "ДАТА И ВРЕМЯ СОХРАНЕНЫ"), zone);
          synced = true;
        } else {
          setPhoneSyncStatus("ERROR");
          showPhoneSyncState(nwText("SYNC NOT SAVED", "НЕ УДАЛОСЬ СОХРАНИТЬ"),
                             nwText("Check RTC / phone", "ПРОВЕРЬ ЧАСЫ И ТЕЛЕФОН"),
                             nwText("Try sync again", "ПОВТОРИ СИНХРОНИЗАЦИЮ"));
        }
        if (synced) break;
      }
      delay(25);
    }

    if (synced) delay(1800); // Give the phone time to read the final status.
    advertising->stop();
    BLEDevice::deinit(true);
    btStop();
    nwTimeSyncStatusCharacteristic = nullptr;

    if (!synced && cancelled) {
      showPhoneSyncState(nwText("SYNC CANCELLED", "СИНХРОНИЗАЦИЯ ОТМЕНЕНА"),
                         nwText("Bluetooth is now off", "BLUETOOTH ВЫКЛЮЧЕН"),
                         nwText("Returning to settings", "ВОЗВРАЩАЮ В НАСТРОЙКИ"));
      delay(1000);
    } else if (!synced) {
      showPhoneSyncState(nwText("SYNC TIMED OUT", "ВРЕМЯ ОЖИДАНИЯ ИСТЕКЛО"),
                         nwText("Open app and retry", "ОТКРОЙ ПРИЛОЖЕНИЕ И ПОВТОРИ"),
                         nwText("Bluetooth is now off", "BLUETOOTH ВЫКЛЮЧЕН"));
      delay(1800);
    }
    waitAllReleased(1200);
    RTC.read(currentTime);
    showNeuroMenu(false);
  }

  void editorHeader(const char *title) {
    display.setFullWindow();
    display.fillScreen(backgroundColor());
    display.setTextColor(foregroundColor());
    display.setTextWrap(false);
    display.drawRect(2, 2, 196, 196, foregroundColor());
    display.fillRect(7, 6, 186, 21, foregroundColor());
    drawTextColor(10, 13, title, backgroundColor());
    label(9, 164, nwText("UP/DN CHANGE   HOLD=FAST", "ВВЕРХ/ВНИЗ: ШАГ  УДЕРЖ.: БЫСТРО"));
    label(9, 177, nwText("MENU: NEXT / SAVE", "МЕНЮ: ДАЛЕЕ / СОХРАНИТЬ"));
    label(9, 188, nwText("BACK: CANCEL   AUTO:60S", "НАЗАД: ОТМЕНА   АВТО:60С"));
  }

  void presentEditorFrame() {
    const bool partial = nwEditorPartial < 7;
    nwEditorPartial = partial ? nwEditorPartial + 1 : 0;
    display.display(partial);
  }

  void editTime(bool alarm = false) {
    guiState = APP_STATE;
    nwAppReturnToMenu = 1;
    RTC.read(currentTime);

    uint8_t hour = alarm ? nwAlarmHour : currentTime.Hour % 24;
    uint8_t minute = alarm ? nwAlarmMinute : currentTime.Minute % 60;
    uint8_t field = 0;
    nwEditorPartial = 0;
    uint32_t lastAction = millis();

    waitAllReleased(1500);

    while ((uint32_t)(millis() - lastAction) < NW_EDITOR_TIMEOUT_MS) {
      editorHeader(alarm ? nwText("SET ALARM TIME", "ВРЕМЯ БУДИЛЬНИКА")
                         : nwText("SET CLOCK TIME", "ВРЕМЯ НА ЧАСАХ"));

      display.setTextSize(3);
      display.setCursor(28, 72);
      if (hour < 10) display.print("0");
      display.print(hour);
      display.setCursor(87, 72);
      display.print(":");
      display.setCursor(109, 72);
      if (minute < 10) display.print("0");
      display.print(minute);
      display.setTextSize(1);

      if (field == 0) display.drawRect(22, 54, 56, 32, foregroundColor());
      else display.drawRect(103, 54, 56, 32, foregroundColor());

      label(31, 104, field == 0 ? nwText("^ HOUR", "^ ЧАС") : nwText("  HOUR", "  ЧАС"));
      label(111, 104, field == 1 ? nwText("^ MIN", "^ МИН") : nwText("  MIN", "  МИН"));
      presentEditorFrame();

      const int button = waitEditorButton(lastAction);
      if (button == 0) break;
      if (button == 1) {
        if (field == 0) {
          field = 1;
        } else {
          if (alarm) {
            nwAlarmHour = hour;
            nwAlarmMinute = minute;
            saveBytePref("alarm_h", nwAlarmHour);
            saveBytePref("alarm_m", nwAlarmMinute);
          } else {
            tmElements_t tm = currentTime;
            tm.Hour = hour;
            tm.Minute = minute;
            tm.Second = 0;
            RTC.set(tm);
          }
          buzzConfirm();
          RTC.read(currentTime);
          showNeuroMenu(false);
          return;
        }
      } else if (button == 2 || button == 5) {
        const uint8_t step = button == 5 ? (field == 0 ? 5 : 10) : 1;
        if (field == 0) hour = (hour + step) % 24;
        else minute = (minute + step) % 60;
      } else if (button == 3 || button == 6) {
        const uint8_t step = button == 6 ? (field == 0 ? 5 : 10) : 1;
        if (field == 0) hour = (hour + 24 - step) % 24;
        else minute = (minute + 60 - step) % 60;
      } else if (button == 4) {
        showNeuroMenu(false);
        return;
      }
    }

    showNeuroMenu(false);
  }

  bool leapYear(int year) {
    return (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
  }

  uint8_t daysInMonth(uint8_t month, int year) {
    static const uint8_t days[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    if (month == 2 && leapYear(year)) return 29;
    if (month < 1 || month > 12) return 31;
    return days[month - 1];
  }

  void editDate() {
    guiState = APP_STATE;
    nwAppReturnToMenu = 1;
    RTC.read(currentTime);

    uint8_t day = currentTime.Day;
    uint8_t month = currentTime.Month;
    int year = tmYearToCalendar(currentTime.Year);
    if (year < 2020 || year > 2099) year = 2026;

    uint8_t field = 0;
    nwEditorPartial = 0;
    uint32_t lastAction = millis();
    waitAllReleased(1500);

    while ((uint32_t)(millis() - lastAction) < NW_EDITOR_TIMEOUT_MS) {
      const uint8_t maxDay = daysInMonth(month, year);
      if (day > maxDay) day = maxDay;

      editorHeader(nwText("SET DATE", "НАСТРОЙКА ДАТЫ"));

      char buf[24];
      const uint8_t first = nwDateDmy ? day : month;
      const uint8_t second = nwDateDmy ? month : day;
      snprintf(buf, sizeof(buf), "%02u.%02u.%04d",
               (unsigned)first, (unsigned)second, year);

      display.setTextSize(2);
      display.setCursor(28, 70);
      display.print(buf);
      display.setTextSize(1);

      if (field == 0) display.drawRect(24, 55, 32, 28, foregroundColor());
      else if (field == 1) display.drawRect(61, 55, 32, 28, foregroundColor());
      else display.drawRect(98, 55, 72, 28, foregroundColor());

      label(28, 105, field == 0 ? (nwDateDmy ? "^ДЕНЬ" : "^МЕС") : (nwDateDmy ? " ДЕНЬ" : " МЕС"));
      label(79, 105, field == 1 ? (nwDateDmy ? "^МЕС" : "^ДЕНЬ") : (nwDateDmy ? " МЕС" : " ДЕНЬ"));
      label(132, 105, field == 2 ? "^ГОД" : " ГОД");
      presentEditorFrame();

      const int button = waitEditorButton(lastAction);
      if (button == 0) break;
      if (button == 1) {
        if (field < 2) {
          field++;
        } else {
          tmElements_t tm = currentTime;
          tm.Day = day;
          tm.Month = month;
          tm.Year = y2kYearToTm(year - 2000);
          RTC.set(tm);
          buzzConfirm();
          RTC.read(currentTime);
          showNeuroMenu(false);
          return;
        }
      } else if (button == 2 || button == 5) {
        const bool editingDay = (field == 0 && nwDateDmy) || (field == 1 && !nwDateDmy);
        const uint8_t step = button == 5 ? (field == 2 ? 10 : (editingDay ? 7 : 3)) : 1;
        if (field < 2 && editingDay) {
          const uint8_t limit = daysInMonth(month, year);
          day = (uint8_t)(((day - 1 + step) % limit) + 1);
        } else if (field < 2) {
          month = (uint8_t)(((month - 1 + step) % 12) + 1);
          const uint8_t limit = daysInMonth(month, year);
          if (day > limit) day = limit;
        } else {
          year = 2020 + ((year - 2020 + step) % 80);
        }
      } else if (button == 3 || button == 6) {
        const bool editingDay = (field == 0 && nwDateDmy) || (field == 1 && !nwDateDmy);
        const uint8_t step = button == 6 ? (field == 2 ? 10 : (editingDay ? 7 : 3)) : 1;
        if (field < 2 && editingDay) {
          const uint8_t limit = daysInMonth(month, year);
          day = (uint8_t)(((day - 1 + limit - (step % limit)) % limit) + 1);
        } else if (field < 2) {
          month = (uint8_t)(((month - 1 + 12 - (step % 12)) % 12) + 1);
          const uint8_t limit = daysInMonth(month, year);
          if (day > limit) day = limit;
        } else {
          year = 2020 + ((year - 2020 + 80 - (step % 80)) % 80);
        }
      } else if (button == 4) {
        showNeuroMenu(false);
        return;
      }
    }

    showNeuroMenu(false);
  }

  int waitEditorButton(uint32_t &lastAction) {
    while ((uint32_t)(millis() - lastAction) < NW_EDITOR_TIMEOUT_MS) {
      int pin = -1;
      int tapCode = 0;
      if (digitalRead(MENU_BTN_PIN)) {
        pin = MENU_BTN_PIN;
        tapCode = 1;
      } else if (digitalRead(UP_BTN_PIN)) {
        pin = UP_BTN_PIN;
        tapCode = 2;
      } else if (digitalRead(DOWN_BTN_PIN)) {
        pin = DOWN_BTN_PIN;
        tapCode = 3;
      } else if (digitalRead(BACK_BTN_PIN)) {
        pin = BACK_BTN_PIN;
        tapCode = 4;
      }

      if (pin >= 0) {
        const uint32_t pressedAt = millis();
        while (digitalRead(pin) && (uint32_t)(millis() - pressedAt) < 900UL)
          delay(20);
        const bool longPress = (uint32_t)(millis() - pressedAt) >= 500UL;
        lastAction = millis();
        waitAllReleased(1200);
        if (tapCode == 2 && longPress) return 5;
        if (tapCode == 3 && longPress) return 6;
        return tapCode;
      }
      delay(25);
    }
    return 0;
  }

  void editStepGoal() {
    guiState = APP_STATE;
    nwAppReturnToMenu = 1;
    uint32_t value = nwStepGoal;
    uint32_t lastAction = millis();
    waitAllReleased(1500);

    while ((uint32_t)(millis() - lastAction) < NW_EDITOR_TIMEOUT_MS) {
      editorHeader(nwText("DAILY STEP GOAL", "ЦЕЛЬ ШАГОВ НА ДЕНЬ"));
      char buf[24];
      snprintf(buf, sizeof(buf), "%lu", (unsigned long)value);
      display.setTextSize(3);
      display.setCursor(value < 10000UL ? 48 : 30, 78);
      display.print(buf);
      display.setTextSize(1);
      label(60, 112, nwText("STEPS / DAY", "ШАГОВ В ДЕНЬ"));
      label(28, 137, nwText("MIN 1000     MAX 30000", "МИН 1000     МАКС 30000"));
      presentEditorFrame();

      const int button = waitEditorButton(lastAction);
      if (button == 0 || button == 4) {
        showNeuroMenu(false);
        return;
      }
      if (button == 1) {
        nwStepGoal = value;
        saveUIntPref("step_goal", nwStepGoal);
        buzzConfirm();
        showNeuroMenu(false);
        return;
      }

      const uint32_t step = button == 5 || button == 6
                                ? NW_STEP_GOAL_HOLD_STEP
                                : NW_STEP_GOAL_STEP;
      if (button == 2 || button == 5) {
        value = value + step > NW_STEP_GOAL_MAX
                    ? NW_STEP_GOAL_MIN
                    : value + step;
      } else if (button == 3 || button == 6) {
        value = value < NW_STEP_GOAL_MIN + step
                    ? NW_STEP_GOAL_MAX
                    : value - step;
      }
    }

    showNeuroMenu(false);
  }

  void resetSteps() {
    guiState = APP_STATE;
    nwAppReturnToMenu = 1;
    waitAllReleased(1200);

    display.setFullWindow();
    display.fillScreen(backgroundColor());
    display.setTextColor(foregroundColor());
    display.drawRect(2, 2, 196, 196, foregroundColor());
    label(12, 18, nwText("RESET STEP COUNTER?", "СБРОСИТЬ СЧЁТЧИК ШАГОВ?"));
    display.drawLine(8, 32, 191, 32, foregroundColor());
    label(18, 75, nwText("MENU  = YES", "МЕНЮ = ДА"));
    label(18, 100, nwText("BACK  = NO", "НАЗАД = НЕТ"));
    label(18, 135, nwText("CURRENT:", "СЕЙЧАС:"));
    char buf[24];
    snprintf(buf, sizeof(buf), "%lu", (unsigned long)sensor.getCounter());
    label(85, 135, buf);
    display.display(false);

    const uint32_t started = millis();
    while ((uint32_t)(millis() - started) < NW_EDITOR_TIMEOUT_MS) {
      if (digitalRead(MENU_BTN_PIN)) {
        waitAllReleased(1200);
        sensor.resetStepCounter();
        buzzConfirm();
        showNeuroMenu(false);
        return;
      }
      if (digitalRead(BACK_BTN_PIN)) {
        waitAllReleased(1200);
        showNeuroMenu(false);
        return;
      }
      delay(20);
    }
    showNeuroMenu(false);
  }

  void showStepsCard() {
    guiState = APP_STATE;
    display.setFullWindow();
    display.fillScreen(backgroundColor());
    display.setTextColor(foregroundColor());
    display.drawRect(2, 2, 196, 196, foregroundColor());
    label(10, 10, nwText("NW://STEPS", "NW://ШАГИ"));

    const uint32_t steps = sensor.getCounter();
    char buf[32];
    snprintf(buf, sizeof(buf), "%lu", (unsigned long)steps);

    display.setTextSize(3);
    display.setCursor(24, 62);
    display.print(buf);
    display.setTextSize(1);

    snprintf(buf, sizeof(buf), nwText("GOAL %lu", "ЦЕЛЬ %lu"), (unsigned long)nwStepGoal);
    label(10, 112, buf);

    const uint32_t capped = steps > nwStepGoal ? nwStepGoal : steps;
    const int fill = (int)((capped * 176UL) / nwStepGoal);
    display.drawRect(10, 130, 180, 14, foregroundColor());
    if (fill > 0) display.fillRect(12, 132, fill, 10, foregroundColor());

    label(10, 176, nwText("ANY BUTTON: BACK", "ЛЮБАЯ КНОПКА: НАЗАД"));
    display.display(false);
  }

  void showDiagnostics() {
    guiState = APP_STATE;
    RTC.read(currentTime);

    display.setFullWindow();
    display.fillScreen(backgroundColor());
    display.setTextColor(foregroundColor());
    display.drawRect(2, 2, 196, 196, foregroundColor());
    label(10, 10, nwText("NW://STATUS", "NW://СТАТУС"));
    display.drawLine(8, 25, 191, 25, foregroundColor());

    char buf[64];
    const float voltage = getBatteryVoltage();
    const int pct = batteryPercent(voltage);
    snprintf(buf, sizeof(buf), nwText("BATTERY: %d%%", "ЗАРЯД: %d%%"), pct < 0 ? 0 : pct);
    label(10, 42, buf);

    snprintf(buf, sizeof(buf), nwText("STEPS: %lu", "ШАГИ: %lu"), (unsigned long)sensor.getCounter());
    label(10, 62, buf);

    snprintf(buf, sizeof(buf), nwText("HEAP: %lu B", "ПАМЯТЬ: %lu Б"),
             (unsigned long)esp_get_free_heap_size());
    label(10, 82, buf);

    snprintf(buf, sizeof(buf), nwText("FLASH: %lu MB", "ФЛЕШ: %lu МБ"),
             (unsigned long)(ESP.getFlashChipSize() / (1024UL * 1024UL)));
    label(10, 102, buf);

    snprintf(buf, sizeof(buf), nwText("CHIP: ESP32-PICO-D4", "ЧИП: ESP32-PICO-D4"));
    label(10, 122, buf);

    snprintf(buf, sizeof(buf), nwText("RTC: %02u:%02u %02u.%02u", "ЧАСЫ: %02u:%02u %02u.%02u"),
             (unsigned)currentTime.Hour,
             (unsigned)currentTime.Minute,
             (unsigned)currentTime.Day,
             (unsigned)currentTime.Month);
    label(10, 142, buf);

    snprintf(buf, sizeof(buf), nwText("ALARM: %s %02u:%02u", "БУДИЛЬНИК: %s %02u:%02u"),
             nwText(nwAlarmEnabled ? "ON" : "OFF", nwAlarmEnabled ? "ВКЛ" : "ВЫКЛ"),
             (unsigned)nwAlarmHour, (unsigned)nwAlarmMinute);
    label(10, 162, buf);

    label(10, 176, nwText("RADIOS: OFF AT REST", "РАДИО: ВЫКЛ В ПОКОЕ"));
    char zone[16];
    formatUtcOffset(zone, sizeof(zone));
    label(120, 176, zone);
    label(10, 188, nwText("ANY BUTTON: BACK", "ЛЮБАЯ КНОПКА: НАЗАД"));
    display.display(false);
  }

  void showAbout() {
    guiState = APP_STATE;
    display.setFullWindow();
    display.fillScreen(backgroundColor());
    display.setTextColor(foregroundColor());
    display.drawRect(2, 2, 196, 196, foregroundColor());
    label(10, 10, nwText("NEUROWATCH OS", "НЕЙРОЧАСЫ ОС"));
    display.drawLine(8, 25, 191, 25, foregroundColor());

    label(10, 45, nwText("VERSION: " NW_VERSION, "ВЕРСИЯ: " NW_VERSION));
    label(10, 66, nwText("FACE: STANDARD DAILY", "ЦИФЕРБЛАТ: СТАНДАРТ"));
    label(10, 87, nwText("UPDATE: USB INSTALLER", "ОБНОВЛЕНИЕ: USB"));
    label(10, 108, nwText("BLE: ON DEMAND ONLY", "BLE: ТОЛЬКО ПО ЗАПРОСУ"));
    label(10, 139, nwText("EDITOR KEYS:", "УПРАВЛЕНИЕ:"));
    label(10, 154, nwText("UP/DN CHANGE; HOLD=FAST", "ВВЕРХ/ВНИЗ: ШАГ; УДЕРЖ.: БЫСТРО"));
    label(10, 169, nwText("MENU:NEXT/SAVE  BACK:CANCEL", "МЕНЮ:ДАЛЕЕ/СОХР.  НАЗАД:ОТМЕНА"));
    label(10, 188, nwText("ANY BUTTON: BACK", "ЛЮБАЯ КНОПКА: НАЗАД"));
    display.display(false);
  }

  void waitAllReleased(uint32_t timeoutMs) {
    pinMode(MENU_BTN_PIN, INPUT);
    pinMode(BACK_BTN_PIN, INPUT);
    pinMode(UP_BTN_PIN, INPUT);
    pinMode(DOWN_BTN_PIN, INPUT);

    const uint32_t start = millis();
    while (digitalRead(MENU_BTN_PIN) || digitalRead(BACK_BTN_PIN) ||
           digitalRead(UP_BTN_PIN) || digitalRead(DOWN_BTN_PIN)) {
      if ((uint32_t)(millis() - start) >= timeoutMs) break;
      delay(10);
    }
    delay(35);
  }
};

NeuroWatch watch(nwSettings);

void setup() {
  loadUserPrefs();
  watch.settings.gmtOffset = (long)nwUtcOffsetMinutes * 60L;
  nwTextRenderer.begin(watch.display);

  // Daily mode never needs radios. Shut them down before Watchy handles the wake
  // reason so cold boots and USB resets do not leave RF blocks powered.
  WiFi.mode(WIFI_OFF);
  btStop();

  watch.init();
}

void loop() {}
