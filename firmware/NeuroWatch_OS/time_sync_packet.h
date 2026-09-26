#pragma once

#include <stddef.h>
#include <stdint.h>

static const size_t NW_TIME_SYNC_PACKET_SIZE = 15;
static const uint8_t NW_TIME_SYNC_PROTOCOL_VERSION = 1;
static const uint8_t NW_TIME_SYNC_COMMAND_SET_LOCAL_TIME = 1;

struct NwLocalTimeSync {
  uint16_t year;
  uint8_t month;
  uint8_t day;
  uint8_t hour;
  uint8_t minute;
  uint8_t second;
  int16_t utcOffsetMinutes;
};

inline uint16_t nwTimeSyncCrc16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xffff;
  for (size_t i = 0; i < length; ++i) {
    crc ^= (uint16_t)data[i] << 8;
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x8000)
                ? (uint16_t)((crc << 1) ^ 0x1021)
                : (uint16_t)(crc << 1);
    }
  }
  return crc;
}

inline bool nwIsLeapYear(uint16_t year) {
  return (year % 4 == 0 && year % 100 != 0) || year % 400 == 0;
}

inline uint8_t nwDaysInMonth(uint8_t month, uint16_t year) {
  static const uint8_t days[] = {31, 28, 31, 30, 31, 30,
                                 31, 31, 30, 31, 30, 31};
  if (month < 1 || month > 12) return 0;
  if (month == 2 && nwIsLeapYear(year)) return 29;
  return days[month - 1];
}

inline bool nwDecodeTimeSyncPacket(const uint8_t *packet,
                                  size_t length,
                                  NwLocalTimeSync &result) {
  if (packet == NULL || length != NW_TIME_SYNC_PACKET_SIZE ||
      packet[0] != 'N' || packet[1] != 'W' ||
      packet[2] != NW_TIME_SYNC_PROTOCOL_VERSION ||
      packet[3] != NW_TIME_SYNC_COMMAND_SET_LOCAL_TIME) {
    return false;
  }

  const uint16_t expectedCrc =
      (uint16_t)packet[13] | ((uint16_t)packet[14] << 8);
  if (nwTimeSyncCrc16(packet, 13) != expectedCrc) return false;

  NwLocalTimeSync decoded;
  decoded.year = (uint16_t)packet[4] | ((uint16_t)packet[5] << 8);
  decoded.month = packet[6];
  decoded.day = packet[7];
  decoded.hour = packet[8];
  decoded.minute = packet[9];
  decoded.second = packet[10];
  const uint16_t rawOffset = (uint16_t)packet[11] | ((uint16_t)packet[12] << 8);
  decoded.utcOffsetMinutes = (int16_t)rawOffset;

  if (decoded.year < 2020 || decoded.year > 2099 ||
      decoded.day < 1 || decoded.day > nwDaysInMonth(decoded.month, decoded.year) ||
      decoded.hour > 23 || decoded.minute > 59 || decoded.second > 59 ||
      decoded.utcOffsetMinutes < -720 || decoded.utcOffsetMinutes > 840) {
    return false;
  }

  result = decoded;
  return true;
}
