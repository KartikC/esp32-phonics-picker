#pragma once

#include <stdint.h>

#include "LayoutGeometry.h"
#include "PlayBreakTimer.h"

namespace phonics_game {

constexpr int16_t kBreakTimerIconTop = 54;
constexpr int16_t kBreakCountdownCenterX = kScreenWidth / 2;
constexpr int16_t kBreakCountdownCenterY = 266;
constexpr uint8_t kBreakCountdownTextSize = 7;
constexpr int16_t kBreakProgressLeft = 64;
constexpr int16_t kBreakProgressTop = 334;
constexpr int16_t kBreakProgressWidth = 240;
constexpr int16_t kBreakProgressHeight = 8;
constexpr int16_t kBreakLabelCenterY = 382;
constexpr uint8_t kBreakLabelTextSize = 3;

inline void formatBreakCountdown(uint32_t remainingSeconds, char output[6]) {
  const uint32_t bounded = remainingSeconds > 99u * 60u + 59u ?
      99u * 60u + 59u : remainingSeconds;
  const uint8_t minutes = static_cast<uint8_t>(bounded / 60u);
  const uint8_t seconds = static_cast<uint8_t>(bounded % 60u);
  output[0] = static_cast<char>('0' + minutes / 10u);
  output[1] = static_cast<char>('0' + minutes % 10u);
  output[2] = ':';
  output[3] = static_cast<char>('0' + seconds / 10u);
  output[4] = static_cast<char>('0' + seconds % 10u);
  output[5] = '\0';
}

inline uint16_t breakProgressPixels(uint32_t remainingMs) {
  const uint32_t bounded = remainingMs > kPlayBreakDurationMs ?
      kPlayBreakDurationMs : remainingMs;
  const uint32_t elapsedMs = kPlayBreakDurationMs - bounded;
  return static_cast<uint16_t>(
      (static_cast<uint64_t>(elapsedMs) * kBreakProgressWidth) /
      kPlayBreakDurationMs);
}

}  // namespace phonics_game
