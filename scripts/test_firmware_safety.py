"""Static safety invariants: additional guards, not hardware simulation."""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] /
          "firmware/NeuroWatch_OS/NeuroWatch_OS.ino").read_text()


class FirmwareSafetyContract(unittest.TestCase):
    def test_no_ble_ota_entry_point(self):
        self.assertNotIn("updateFWBegin(", SOURCE)

    def test_watchface_does_not_start_radio_on_single_back_press(self):
        # Compare top-level branch boundaries, rather than whole source.
        block = SOURCE.split("if (guiState == WATCHFACE_STATE) {", 1)[1].split(
            "} else if (guiState == MAIN_MENU_STATE) {", 1)[0]
        self.assertNotIn("runSafeUpdater(", block)

    def test_wifi_update_must_check_dual_partition_and_voltage(self):
        updater = SOURCE.split("void runSafeUpdater() {", 1)[1]
        self.assertIn("safeOtaPartition()", updater)
        self.assertIn("NW_MIN_OTA_VOLTAGE", updater)
        self.assertIn("manager.startConfigPortal(", updater)

    def test_wifi_password_generated_fresh(self):
        self.assertIn("esp_random()", SOURCE)
        self.assertNotRegex(SOURCE, r"WiFi\.begin\(\s*[\"']")

    def test_menu_partial_refresh_is_bounded(self):
        self.assertIn("showNeuroMenu(true)", SOURCE)
        self.assertIn("menuPartialRefreshes < 6", SOURCE)
        self.assertIn("display.display(partial)", SOURCE)

    def test_battery_does_not_use_float_printf(self):
        self.assertNotIn("%.2f", SOURCE)
        self.assertIn("centivolts", SOURCE)

    def test_ota_requires_large_slots_and_otadata(self):
        self.assertIn("ESP_PARTITION_SUBTYPE_DATA_OTA", SOURCE)
        self.assertIn("NW_MIN_OTA_SLOT_BYTES", SOURCE)
        self.assertIn("running->address != a->address", SOURCE)

    def test_same_face_does_not_rewrite_nvs(self):
        self.assertIn("if (previous != retainedFace)", SOURCE)

    def test_vector_clock_uses_no_large_bitmap_font(self):
        self.assertNotIn("FreeMonoBold18pt7b.h", SOURCE)
        self.assertIn("void digit(int x, int y, uint8_t value)", SOURCE)
        self.assertIn("digit(25, 31, hour / 10)", SOURCE)

    def test_no_flash_partition_or_bootloader_writes(self):
        self.assertNotIn("esp_partition_write(", SOURCE)
        self.assertNotIn("esp_flash_write(", SOURCE)


if __name__ == "__main__":
    unittest.main()
