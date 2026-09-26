"""Host-compiled tests for alarm scheduling and the BLE time packet."""
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware/NeuroWatch_OS"


def compile_and_run(test_case, header, source):
    header_path = FIRMWARE / header
    test_case.assertTrue(header_path.is_file(), f"missing production header: {header_path}")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "test.cpp"
        binary = Path(tmp) / "test-watch-logic"
        src.write_text(source)
        build = subprocess.run(
            ["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
             "-I", str(FIRMWARE), str(src), "-o", str(binary)],
            capture_output=True, text=True,
        )
        test_case.assertEqual(build.returncode, 0, build.stderr)
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        test_case.assertEqual(run.returncode, 0, run.stderr)


class WatchLogicTests(unittest.TestCase):
    def test_alarm_fires_at_configured_minute_only_once_per_day(self):
        compile_and_run(self, "alarm_policy.h", r'''#include <cassert>
#include <stdint.h>
#include "alarm_policy.h"
int main() {
  uint32_t lastDay = 0xffffffffUL;
  assert(!nwShouldFireDailyAlarm(false, 7, 0, 7, 0, 20260926UL, lastDay));
  assert(!nwShouldFireDailyAlarm(true, 6, 59, 7, 0, 20260926UL, lastDay));
  assert(nwShouldFireDailyAlarm(true, 7, 0, 7, 0, 20260926UL, lastDay));
  assert(lastDay == 20260926UL);
  assert(!nwShouldFireDailyAlarm(true, 7, 0, 7, 0, 20260926UL, lastDay));
  assert(nwShouldFireDailyAlarm(true, 7, 0, 7, 0, 20260927UL, lastDay));
}
''')

    def test_alarm_vibration_can_be_disabled_without_disabling_alarm(self):
        compile_and_run(self, "alarm_policy.h", r'''#include <cassert>
#include "alarm_policy.h"
int main() {
  uint32_t lastDay = 0xffffffffUL;
  const bool alarmTriggered =
      nwShouldFireDailyAlarm(true, 7, 0, 7, 0, 20260926UL, lastDay);
  assert(alarmTriggered);
  assert(!nwShouldVibrateAlarm(true, false));
  assert(nwShouldVibrateAlarm(true, true));
  assert(!nwShouldVibrateAlarm(false, true));
}
''')

    def test_phone_packet_sets_local_date_time_and_yekaterinburg_offset(self):
        compile_and_run(self, "time_sync_packet.h", r'''#include <cassert>
#include <stdint.h>
#include "time_sync_packet.h"
int main() {
  const uint8_t packet[15] = {78,87,1,1,234,7,9,27,1,29,18,44,1,158,200};
  NwLocalTimeSync value = {};
  assert(nwDecodeTimeSyncPacket(packet, sizeof(packet), value));
  assert(value.year == 2026 && value.month == 9 && value.day == 27);
  assert(value.hour == 1 && value.minute == 29 && value.second == 18);
  assert(value.utcOffsetMinutes == 300);
}
''')

    def test_phone_packet_rejects_corruption_invalid_date_and_out_of_range_offset(self):
        compile_and_run(self, "time_sync_packet.h", r'''#include <cassert>
#include <stdint.h>
#include "time_sync_packet.h"
int main() {
  const uint8_t valid[15] = {78,87,1,1,234,7,9,27,1,29,18,44,1,158,200};
  const uint8_t badDate[15] = {78,87,1,1,234,7,2,30,1,29,18,44,1,176,192};
  const uint8_t badHour[15] = {78,87,1,1,234,7,9,27,25,29,18,44,1,233,206};
  const uint8_t badOffset[15] = {78,87,1,1,234,7,9,27,1,29,18,132,3,11,124};
  NwLocalTimeSync value = {};
  uint8_t damaged[15];
  for (int i = 0; i < 15; ++i) damaged[i] = valid[i];
  damaged[14] ^= 1;
  assert(!nwDecodeTimeSyncPacket(damaged, sizeof(damaged), value));
  assert(!nwDecodeTimeSyncPacket(badDate, sizeof(badDate), value));
  assert(!nwDecodeTimeSyncPacket(badHour, sizeof(badHour), value));
  assert(!nwDecodeTimeSyncPacket(badOffset, sizeof(badOffset), value));
  assert(!nwDecodeTimeSyncPacket(valid, sizeof(valid) - 1, value));
}
''')

    def test_phone_packet_preserves_negative_utc_offset(self):
        compile_and_run(self, "time_sync_packet.h", r'''#include <cassert>
#include <stdint.h>
#include "time_sync_packet.h"
int main() {
  const uint8_t packet[15] = {78,87,1,1,234,7,9,27,1,29,18,212,254,6,76};
  NwLocalTimeSync value = {};
  assert(nwDecodeTimeSyncPacket(packet, sizeof(packet), value));
  assert(value.utcOffsetMinutes == -300);
}
''')


if __name__ == "__main__":
    unittest.main()
