"""Static safety/UX invariants for NeuroWatch OS v0.8."""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] /
          "firmware/NeuroWatch_OS/NeuroWatch_OS.ino").read_text()
CONFIG = (Path(__file__).resolve().parents[1] /
          "firmware/NeuroWatch_OS/neuro_config.h").read_text()


class FirmwareSafetyContract(unittest.TestCase):
    def test_no_legacy_ble_or_wifi_updater(self):
        self.assertNotIn("updateFWBegin(", SOURCE)
        self.assertNotIn("WiFiManager", SOURCE)
        self.assertNotIn("startConfigPortal(", SOURCE)
        self.assertNotIn("WiFi.begin(", SOURCE)

    def test_watchface_does_not_start_radio(self):
        block = SOURCE.split("void drawWatchFace() override {", 1)[1].split(
            "void handleButtonPress() override {", 1)[0]
        self.assertNotIn("WiFi.", block)
        self.assertNotIn("Bluetooth", block)
        self.assertIn("WiFi.mode(WIFI_OFF);", SOURCE)
        self.assertIn("btStop();", SOURCE)

    def test_single_standard_face(self):
        self.assertIn("drawStandardWallpaper()", SOURCE)
        self.assertIn("FACE: STANDARD DAILY", SOURCE)
        self.assertNotIn("retainedFace", SOURCE)

    def test_menu_partial_refresh_is_bounded(self):
        self.assertIn("showNeuroMenu(true)", SOURCE)
        self.assertIn("nwMenuPartial < 8", SOURCE)
        self.assertIn("display.display(partial)", SOURCE)

    def test_battery_avoids_float_printf(self):
        self.assertNotIn("%.2f", SOURCE)
        self.assertIn("batteryPercent(float voltage)", SOURCE)
        self.assertIn("const unsigned cv", SOURCE)

    def test_vector_clock_uses_no_large_bitmap_font(self):
        self.assertNotIn("FreeMonoBold18pt7b.h", SOURCE)
        self.assertIn("void digit(int x, int y, uint8_t value)", SOURCE)
        self.assertIn("digit(20, 37, shownHour / 10)", SOURCE)
        self.assertIn("digit(141, 37, currentTime.Minute % 10)", SOURCE)

    def test_time_and_date_are_separate_easy_editors(self):
        self.assertIn("void editTime(bool alarm = false)", SOURCE)
        self.assertIn("void editDate()", SOURCE)
        self.assertGreaterEqual(SOURCE.count("RTC.set(tm);"), 2)
        self.assertIn("daysInMonth", SOURCE)
        self.assertIn("leapYear", SOURCE)
        self.assertIn("SET CLOCK TIME", SOURCE)
        self.assertIn("HOLD=FAST", SOURCE)
        self.assertIn("NW_EDITOR_TIMEOUT_MS 60000UL", CONFIG)

    def test_settings_are_persistent_but_cached_in_rtc_memory(self):
        self.assertIn("RTC_DATA_ATTR uint32_t nwPrefMagic", SOURCE)
        self.assertIn("if (nwPrefMagic == NW_PREF_MAGIC) return;", SOURCE)
        for key in ('"24h"', '"dmy"', '"vib"', '"hourbuzz"'):
            self.assertIn(key, SOURCE)

    def test_step_counter_and_quick_cards_exist(self):
        self.assertIn("sensor.getCounter()", SOURCE)
        self.assertIn("showStepsCard()", SOURCE)
        self.assertIn("RESET STEPS", SOURCE)
        self.assertIn("NW_STEP_GOAL", SOURCE)
        self.assertIn("editStepGoal()", SOURCE)
        self.assertIn('saveUIntPref("step_goal", nwStepGoal)', SOURCE)

    def test_daily_alarm_is_configurable_and_fires_once_per_day(self):
        self.assertIn("maybeDailyAlarm()", SOURCE)
        self.assertIn("nwAlarmLastDay", SOURCE)
        self.assertIn('saveBoolPref("alarm_on", nwAlarmEnabled)', SOURCE)
        self.assertIn('saveBytePref("alarm_h", nwAlarmHour)', SOURCE)
        self.assertIn('saveBytePref("alarm_m", nwAlarmMinute)', SOURCE)

    def test_existing_v07_preferences_are_migrated(self):
        self.assertIn('prefs.getBool("24h", NW_DEFAULT_24H)', SOURCE)
        self.assertIn('prefs.getBool("dmy", NW_DEFAULT_DMY)', SOURCE)
        self.assertIn('prefs.getBool("vib", NW_DEFAULT_VIBRATION)', SOURCE)
        self.assertIn('prefs.getBool("hourbuzz", NW_DEFAULT_HOURLY_BUZZ)', SOURCE)
        self.assertIn('NW_PREF_MAGIC = 0x4E573038UL', SOURCE)

    def test_hourly_buzz_is_guarded_against_repeat(self):
        self.assertIn("nwHourlyBuzz", SOURCE)
        self.assertIn("nwLastBuzzStamp", SOURCE)
        self.assertIn("if (stamp == nwLastBuzzStamp) return;", SOURCE)

    def test_no_flash_partition_or_bootloader_writes(self):
        self.assertNotIn("esp_partition_write(", SOURCE)
        self.assertNotIn("esp_flash_write(", SOURCE)
        self.assertNotIn("eraseFlash", SOURCE)


if __name__ == "__main__":
    unittest.main()
