#pragma once

#include <stdint.h>

inline bool nwShouldFireDailyAlarm(bool enabled,
                                   uint8_t currentHour,
                                   uint8_t currentMinute,
                                   uint8_t alarmHour,
                                   uint8_t alarmMinute,
                                   uint32_t dayStamp,
                                   uint32_t &lastFiredDay) {
  if (!enabled || currentHour > 23 || currentMinute > 59 ||
      alarmHour > 23 || alarmMinute > 59 ||
      currentHour != alarmHour || currentMinute != alarmMinute ||
      dayStamp == lastFiredDay) {
    return false;
  }

  lastFiredDay = dayStamp;
  return true;
}

inline bool nwShouldVibrateAlarm(bool alarmTriggered, bool vibrationEnabled) {
  return alarmTriggered && vibrationEnabled;
}
