#pragma once

#include <stdint.h>
#include <stddef.h>

// These checks run before switching the radio on and before writing any bytes.
// The running/target partition pointers and OTA data partition are inspected
// through ESP-IDF at runtime; a build-time partition CSV alone is insufficient.
inline bool nwCanStartWifiOta(uint32_t runningOffset, uint32_t targetOffset,
                              uint32_t targetSize, uint32_t currentImageSize,
                              bool hasOtaData, int batteryPercent) {
  return hasOtaData && batteryPercent >= 50 &&
         runningOffset >= 0x10000UL && targetOffset >= 0x10000UL &&
         runningOffset != targetOffset &&
         targetSize >= currentImageSize &&
         targetSize >= 64UL * 1024UL &&
         targetOffset < 4UL * 1024UL * 1024UL &&
         targetSize <= 4UL * 1024UL * 1024UL - targetOffset;
}

inline bool nwOtaChunkFits(uint32_t alreadyWritten, size_t chunkSize,
                           uint32_t targetSize) {
  return chunkSize > 0 && alreadyWritten <= targetSize &&
         chunkSize <= targetSize - alreadyWritten;
}
