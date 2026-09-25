#include <Arduino.h>
#include <Watchy.h>
#include <Preferences.h>
#include <WiFi.h>
#include "neuro_config.h"

// NeuroWatch OS v0.8 - one standard face, quicker settings and low-overhead daily use.
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

static constexpr uint32_t NW_PREF_MAGIC = 0x4E573038UL; // "NW08"; migrates v0.7 settings once.
RTC_DATA_ATTR uint32_t nwPrefMagic = 0;
RTC_DATA_ATTR uint8_t nwUse24h = NW_DEFAULT_24H;
RTC_DATA_ATTR uint8_t nwDateDmy = NW_DEFAULT_DMY;
RTC_DATA_ATTR uint8_t nwVibration = NW_DEFAULT_VIBRATION;
RTC_DATA_ATTR uint8_t nwHourlyBuzz = NW_DEFAULT_HOURLY_BUZZ;
RTC_DATA_ATTR uint8_t nwAlarmEnabled = NW_DEFAULT_ALARM_ENABLED;
RTC_DATA_ATTR uint8_t nwAlarmHour = NW_DEFAULT_ALARM_HOUR;
RTC_DATA_ATTR uint8_t nwAlarmMinute = NW_DEFAULT_ALARM_MINUTE;
RTC_DATA_ATTR uint32_t nwStepGoal = NW_STEP_GOAL;
RTC_DATA_ATTR uint32_t nwAlarmLastDay = 0xFFFFFFFFUL;
RTC_DATA_ATTR uint8_t nwMenuPartial = 0;
RTC_DATA_ATTR uint8_t nwAppReturnToMenu = 0;
RTC_DATA_ATTR uint32_t nwLastBuzzStamp = 0xFFFFFFFFUL;

static void loadUserPrefs() {
  if (nwPrefMagic == NW_PREF_MAGIC) return;

  Preferences prefs;
  if (prefs.begin("nw-os", true)) {
    nwUse24h = prefs.getBool("24h", NW_DEFAULT_24H);
    nwDateDmy = prefs.getBool("dmy", NW_DEFAULT_DMY);
    nwVibration = prefs.getBool("vib", NW_DEFAULT_VIBRATION);
    nwHourlyBuzz = prefs.getBool("hourbuzz", NW_DEFAULT_HOURLY_BUZZ);
    nwAlarmEnabled = prefs.getBool("alarm_on", NW_DEFAULT_ALARM_ENABLED);
    nwAlarmHour = prefs.getUChar("alarm_h", NW_DEFAULT_ALARM_HOUR);
    nwAlarmMinute = prefs.getUChar("alarm_m", NW_DEFAULT_ALARM_MINUTE);
    nwStepGoal = prefs.getUInt("step_goal", NW_STEP_GOAL);
    prefs.end();
  } else {
    nwUse24h = NW_DEFAULT_24H;
    nwDateDmy = NW_DEFAULT_DMY;
    nwVibration = NW_DEFAULT_VIBRATION;
    nwHourlyBuzz = NW_DEFAULT_HOURLY_BUZZ;
    nwAlarmEnabled = NW_DEFAULT_ALARM_ENABLED;
    nwAlarmHour = NW_DEFAULT_ALARM_HOUR;
    nwAlarmMinute = NW_DEFAULT_ALARM_MINUTE;
    nwStepGoal = NW_STEP_GOAL;
  }
  if (nwAlarmHour > 23) nwAlarmHour = NW_DEFAULT_ALARM_HOUR;
  if (nwAlarmMinute > 59) nwAlarmMinute = NW_DEFAULT_ALARM_MINUTE;
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

class NeuroWatch : public Watchy {
 public:
  using Watchy::Watchy;

  void drawWatchFace() override {
    if (!maybeDailyAlarm()) maybeHourlyBuzz();

    display.setFullWindow();
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
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
    display.fillRect(93, 49, 4, 4, GxEPD_BLACK);
    display.fillRect(93, 63, 4, 4, GxEPD_BLACK);
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
    label(10, 90, buf);

    if (!nwUse24h) {
      label(171, 29, pm ? "PM" : "AM");
    } else {
      label(171, 29, "24");
    }

    drawBatteryWidget(10, 111);
    drawStepsWidget(10, 137);

    if (nwAlarmEnabled) {
      char alarm[20];
      snprintf(alarm, sizeof(alarm), "ALARM %02u:%02u",
               (unsigned)nwAlarmHour, (unsigned)nwAlarmMinute);
      label(10, 153, alarm);
    } else {
      label(10, 153, "ALARM OFF");
    }

    display.drawLine(8, 169, 191, 169, GxEPD_BLACK);
    label(10, 176, "UP:STEPS  DN:STATUS");
    label(10, 188, "MENU:SETTINGS   NW " NW_VERSION);
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
  static constexpr int MENU_COUNT = 12;

  void drawStandardWallpaper() {
    display.drawRect(2, 2, 196, 196, GxEPD_BLACK);
    display.drawLine(8, 25, 191, 25, GxEPD_BLACK);
    label(10, 9, "NEUROWATCH // DAILY");
    label(153, 9, "OS " NW_VERSION);

    // One built-in standard wallpaper: light technical corner marks.
    display.drawLine(8, 31, 27, 31, GxEPD_BLACK);
    display.drawLine(8, 31, 8, 50, GxEPD_BLACK);
    display.drawLine(191, 31, 172, 31, GxEPD_BLACK);
    display.drawLine(191, 31, 191, 50, GxEPD_BLACK);
    display.drawLine(8, 164, 27, 164, GxEPD_BLACK);
    display.drawLine(8, 164, 8, 153, GxEPD_BLACK);
    display.drawLine(191, 164, 172, 164, GxEPD_BLACK);
    display.drawLine(191, 164, 191, 153, GxEPD_BLACK);
  }

  void label(int x, int y, const char *s) {
    display.setFont(nullptr);
    display.setTextSize(1);
    display.setTextColor(GxEPD_BLACK);
    display.setCursor(x, y);
    display.print(s);
  }

  const char *weekdayName() {
    static const char *const names[] = {
        "SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"};
    tmElements_t copy = currentTime;
    const uint8_t day = weekday(makeTime(copy));
    if (day < 1 || day > 7) return "---";
    return names[day - 1];
  }

  void digit(int x, int y, uint8_t value) {
    static const uint8_t segments[10] = {
        0x3f, 0x06, 0x5b, 0x4f, 0x66,
        0x6d, 0x7d, 0x07, 0x7f, 0x6f};
    const uint8_t bits = segments[value % 10];
    constexpr int w = 29, h = 38, t = 4, mid = h / 2;
    if (bits & 0x01) display.fillRect(x + t, y, w - 2 * t, t, GxEPD_BLACK);
    if (bits & 0x02) display.fillRect(x + w - t, y + t, t, mid - t, GxEPD_BLACK);
    if (bits & 0x04) display.fillRect(x + w - t, y + mid, t, mid - t, GxEPD_BLACK);
    if (bits & 0x08) display.fillRect(x + t, y + h - t, w - 2 * t, t, GxEPD_BLACK);
    if (bits & 0x10) display.fillRect(x, y + mid, t, mid - t, GxEPD_BLACK);
    if (bits & 0x20) display.fillRect(x, y + t, t, mid - t, GxEPD_BLACK);
    if (bits & 0x40) display.fillRect(x + t, y + mid - t / 2, w - 2 * t, t, GxEPD_BLACK);
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
      snprintf(buf, sizeof(buf), "BAT --%%");
    } else {
      snprintf(buf, sizeof(buf), "BAT %3d%%", pct);
    }
    label(x, y, buf);

    display.drawRect(72, y - 2, 82, 10, GxEPD_BLACK);
    display.fillRect(154, y + 1, 3, 4, GxEPD_BLACK);
    if (pct > 0) {
      const int fill = (pct * 78) / 100;
      display.fillRect(74, y, fill, 6, GxEPD_BLACK);
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
    snprintf(buf, sizeof(buf), "STEPS %lu", (unsigned long)steps);
    label(x, y, buf);

    const uint32_t capped = steps > nwStepGoal ? nwStepGoal : steps;
    display.drawRect(82, y - 2, 109, 10, GxEPD_BLACK);
    const int fill = (int)((capped * 105UL) / nwStepGoal);
    if (fill > 0) display.fillRect(84, y, fill, 6, GxEPD_BLACK);
  }

  void maybeHourlyBuzz() {
    if (!nwHourlyBuzz || currentTime.Minute != 0) return;
    const uint32_t stamp =
        (uint32_t)currentTime.Month * 10000UL +
        (uint32_t)currentTime.Day * 100UL +
        (uint32_t)currentTime.Hour;
    if (stamp == nwLastBuzzStamp) return;
    nwLastBuzzStamp = stamp;
    vibMotor(50, 4);
  }

  bool maybeDailyAlarm() {
    if (!nwAlarmEnabled || currentTime.Hour != nwAlarmHour ||
        currentTime.Minute != nwAlarmMinute) return false;

    const uint32_t year = (uint32_t)tmYearToCalendar(currentTime.Year);
    const uint32_t dayStamp = ((year * 13UL + currentTime.Month) * 32UL) +
                              currentTime.Day;
    if (dayStamp == nwAlarmLastDay) return false;

    nwAlarmLastDay = dayStamp;
    vibMotor(70, 8);
    return true;
  }

  void buzzConfirm() {
    if (nwVibration) vibMotor(35, 2);
  }

  void menuLabel(int item, char *buf, size_t size) {
    switch (item) {
      case 0: snprintf(buf, size, "SET TIME"); break;
      case 1: snprintf(buf, size, "SET DATE"); break;
      case 2: snprintf(buf, size, "24H MODE         %s", nwUse24h ? "ON" : "OFF"); break;
      case 3: snprintf(buf, size, "DATE FORMAT      %s", nwDateDmy ? "DD.MM" : "MM/DD"); break;
      case 4: snprintf(buf, size, "BUTTON VIB       %s", nwVibration ? "ON" : "OFF"); break;
      case 5: snprintf(buf, size, "HOURLY BUZZ      %s", nwHourlyBuzz ? "ON" : "OFF"); break;
      case 6: snprintf(buf, size, "DAILY ALARM      %s", nwAlarmEnabled ? "ON" : "OFF"); break;
      case 7: snprintf(buf, size, "ALARM TIME    %02u:%02u", (unsigned)nwAlarmHour, (unsigned)nwAlarmMinute); break;
      case 8: snprintf(buf, size, "STEP GOAL      %5lu", (unsigned long)nwStepGoal); break;
      case 9: snprintf(buf, size, "RESET STEPS"); break;
      case 10: snprintf(buf, size, "DIAGNOSTICS"); break;
      default: snprintf(buf, size, "ABOUT / UPDATE"); break;
    }
  }

  void showNeuroMenu(bool requestPartial) {
    display.setFullWindow();
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
    display.setTextWrap(false);

    label(7, 8, "NW://SETTINGS");
    display.drawLine(5, 23, 194, 23, GxEPD_BLACK);

    int top = menuIndex - 2;
    if (top < 0) top = 0;
    const int maxTop = MENU_COUNT - NW_MENU_VISIBLE_ROWS;
    if (top > maxTop) top = maxTop;

    char buf[34];
    for (int row = 0; row < NW_MENU_VISIBLE_ROWS; ++row) {
      const int item = top + row;
      const int y = 32 + row * 28;
      menuLabel(item, buf, sizeof(buf));
      if (item == menuIndex) {
        display.fillRect(5, y - 4, 190, 21, GxEPD_BLACK);
        display.setTextColor(GxEPD_WHITE);
      } else {
        display.setTextColor(GxEPD_BLACK);
      }
      display.setFont(nullptr);
      display.setTextSize(1);
      display.setCursor(10, y);
      display.print(buf);
    }

    display.setTextColor(GxEPD_BLACK);
    display.drawLine(5, 176, 194, 176, GxEPD_BLACK);
    label(7, 184, "UP/DN MOVE  M:OK  B:BACK");

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
        if (nwVibration) vibMotor(35, 2);
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
        editStepGoal();
        return;
      case 9:
        resetSteps();
        return;
      case 10:
        nwAppReturnToMenu = 1;
        showDiagnostics();
        return;
      default:
        nwAppReturnToMenu = 1;
        showAbout();
        return;
    }
  }

  void editorHeader(const char *title) {
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
    display.setTextWrap(false);
    display.drawRect(2, 2, 196, 196, GxEPD_BLACK);
    label(9, 10, title);
    display.drawLine(7, 26, 192, 26, GxEPD_BLACK);
    label(9, 164, "UP/DN CHANGE   HOLD=FAST");
    label(9, 177, "MENU: NEXT / SAVE");
    label(9, 188, "BACK: CANCEL   AUTO:60S");
  }

  void editTime(bool alarm = false) {
    guiState = APP_STATE;
    nwAppReturnToMenu = 1;
    RTC.read(currentTime);

    uint8_t hour = alarm ? nwAlarmHour : currentTime.Hour % 24;
    uint8_t minute = alarm ? nwAlarmMinute : currentTime.Minute % 60;
    uint8_t field = 0;
    uint32_t lastAction = millis();

    waitAllReleased(1500);

    while ((uint32_t)(millis() - lastAction) < NW_EDITOR_TIMEOUT_MS) {
      editorHeader(alarm ? "SET ALARM TIME" : "SET CLOCK TIME");

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

      if (field == 0) display.drawRect(22, 54, 56, 32, GxEPD_BLACK);
      else display.drawRect(103, 54, 56, 32, GxEPD_BLACK);

      label(31, 104, field == 0 ? "^ HOUR" : "  HOUR");
      label(111, 104, field == 1 ? "^ MIN" : "  MIN");
      display.display(true);

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
    uint32_t lastAction = millis();
    waitAllReleased(1500);

    while ((uint32_t)(millis() - lastAction) < NW_EDITOR_TIMEOUT_MS) {
      const uint8_t maxDay = daysInMonth(month, year);
      if (day > maxDay) day = maxDay;

      editorHeader("SET DATE");

      char buf[24];
      const uint8_t first = nwDateDmy ? day : month;
      const uint8_t second = nwDateDmy ? month : day;
      snprintf(buf, sizeof(buf), "%02u.%02u.%04d",
               (unsigned)first, (unsigned)second, year);

      display.setTextSize(2);
      display.setCursor(28, 70);
      display.print(buf);
      display.setTextSize(1);

      if (field == 0) display.drawRect(24, 55, 32, 28, GxEPD_BLACK);
      else if (field == 1) display.drawRect(61, 55, 32, 28, GxEPD_BLACK);
      else display.drawRect(98, 55, 72, 28, GxEPD_BLACK);

      label(28, 105, field == 0 ? (nwDateDmy ? "^DAY" : "^MON") : (nwDateDmy ? " DAY" : " MON"));
      label(79, 105, field == 1 ? (nwDateDmy ? "^MON" : "^DAY") : (nwDateDmy ? " MON" : " DAY"));
      label(132, 105, field == 2 ? "^YEAR" : " YEAR");
      display.display(true);

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
      editorHeader("DAILY STEP GOAL");
      char buf[24];
      snprintf(buf, sizeof(buf), "%lu", (unsigned long)value);
      display.setTextSize(3);
      display.setCursor(value < 10000UL ? 48 : 30, 78);
      display.print(buf);
      display.setTextSize(1);
      label(60, 112, "STEPS / DAY");
      label(28, 137, "MIN 1000     MAX 30000");
      display.display(true);

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
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
    display.drawRect(2, 2, 196, 196, GxEPD_BLACK);
    label(12, 18, "RESET STEP COUNTER?");
    display.drawLine(8, 32, 191, 32, GxEPD_BLACK);
    label(18, 75, "MENU  = YES");
    label(18, 100, "BACK  = NO");
    label(18, 135, "CURRENT:");
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
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
    display.drawRect(2, 2, 196, 196, GxEPD_BLACK);
    label(10, 10, "NW://STEPS");

    const uint32_t steps = sensor.getCounter();
    char buf[32];
    snprintf(buf, sizeof(buf), "%lu", (unsigned long)steps);

    display.setTextSize(3);
    display.setCursor(24, 62);
    display.print(buf);
    display.setTextSize(1);

    snprintf(buf, sizeof(buf), "GOAL %lu", (unsigned long)nwStepGoal);
    label(10, 112, buf);

    const uint32_t capped = steps > nwStepGoal ? nwStepGoal : steps;
    const int fill = (int)((capped * 176UL) / nwStepGoal);
    display.drawRect(10, 130, 180, 14, GxEPD_BLACK);
    if (fill > 0) display.fillRect(12, 132, fill, 10, GxEPD_BLACK);

    label(10, 176, "ANY BUTTON: BACK");
    display.display(false);
  }

  void showDiagnostics() {
    guiState = APP_STATE;
    RTC.read(currentTime);

    display.setFullWindow();
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
    display.drawRect(2, 2, 196, 196, GxEPD_BLACK);
    label(10, 10, "NW://STATUS");
    display.drawLine(8, 25, 191, 25, GxEPD_BLACK);

    char buf[34];
    const float voltage = getBatteryVoltage();
    const int pct = batteryPercent(voltage);
    snprintf(buf, sizeof(buf), "BATTERY: %d%%", pct < 0 ? 0 : pct);
    label(10, 42, buf);

    snprintf(buf, sizeof(buf), "STEPS: %lu", (unsigned long)sensor.getCounter());
    label(10, 62, buf);

    snprintf(buf, sizeof(buf), "HEAP: %lu B", (unsigned long)esp_get_free_heap_size());
    label(10, 82, buf);

    snprintf(buf, sizeof(buf), "FLASH: %lu MB",
             (unsigned long)(ESP.getFlashChipSize() / (1024UL * 1024UL)));
    label(10, 102, buf);

    snprintf(buf, sizeof(buf), "CHIP: ESP32-PICO-D4");
    label(10, 122, buf);

    snprintf(buf, sizeof(buf), "RTC: %02u:%02u %02u.%02u",
             (unsigned)currentTime.Hour,
             (unsigned)currentTime.Minute,
             (unsigned)currentTime.Day,
             (unsigned)currentTime.Month);
    label(10, 142, buf);

    snprintf(buf, sizeof(buf), "ALARM: %s %02u:%02u",
             nwAlarmEnabled ? "ON" : "OFF",
             (unsigned)nwAlarmHour, (unsigned)nwAlarmMinute);
    label(10, 162, buf);

    label(10, 176, "RADIOS: OFF AT REST");
    label(10, 188, "ANY BUTTON: BACK");
    display.display(false);
  }

  void showAbout() {
    guiState = APP_STATE;
    display.setFullWindow();
    display.fillScreen(GxEPD_WHITE);
    display.setTextColor(GxEPD_BLACK);
    display.drawRect(2, 2, 196, 196, GxEPD_BLACK);
    label(10, 10, "NEUROWATCH OS");
    display.drawLine(8, 25, 191, 25, GxEPD_BLACK);

    label(10, 45, "VERSION: " NW_VERSION);
    label(10, 66, "FACE: STANDARD DAILY");
    label(10, 87, "UPDATE: USB INSTALLER");
    label(10, 108, "WIFI/BT: DISABLED AT REST");
    label(10, 139, "EDITOR KEYS:");
    label(10, 154, "UP/DN CHANGE; HOLD=FAST");
    label(10, 169, "MENU:NEXT/SAVE  BACK:CANCEL");
    label(10, 188, "ANY BUTTON: BACK");
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

  // Daily mode never needs radios. Shut them down before Watchy handles the wake
  // reason so cold boots and USB resets do not leave RF blocks powered.
  WiFi.mode(WIFI_OFF);
  btStop();

  watch.init();
}

void loop() {}
