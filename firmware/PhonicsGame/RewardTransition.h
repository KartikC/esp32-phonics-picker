#pragma once

#include <stdint.h>

#include "GameEngine.h"

namespace phonics_game {

// The creature (and its name label) belongs only to the full-water hold and
// recede phases. Keeping this boundary in the transition helper prevents it
// from leaking into the card confirmation/rise or terminal black beat.
inline bool rewardCreatureVisible(uint32_t elapsedMs) {
  return elapsedMs >= kWaterRiseEndMs && elapsedMs < kWaterRecedeEndMs;
}

// Pure transition geometry shared by the firmware renderer and host tests.
// The surface starts below the display, rises to the top, holds while the
// creature is visible, then recedes completely before the next round begins.
inline int16_t rewardWaterSurfaceY(uint32_t elapsedMs,
                                   uint16_t displayHeight) {
  if (elapsedMs < kCorrectPulseEndMs) {
    return static_cast<int16_t>(displayHeight);
  }
  if (elapsedMs < kWaterRiseEndMs) {
    const uint32_t transition = elapsedMs - kCorrectPulseEndMs;
    return static_cast<int16_t>(displayHeight) - static_cast<int16_t>(
        transition * displayHeight /
        (kWaterRiseEndMs - kCorrectPulseEndMs));
  }
  if (elapsedMs < kCreatureRewardEndMs) return 0;
  if (elapsedMs >= kWaterRecedeEndMs) {
    return static_cast<int16_t>(displayHeight);
  }

  const uint32_t transition = elapsedMs - kCreatureRewardEndMs;
  const uint32_t surface = transition * displayHeight /
      (kWaterRecedeEndMs - kCreatureRewardEndMs);
  return surface >= displayHeight
      ? static_cast<int16_t>(displayHeight)
      : static_cast<int16_t>(surface);
}

}  // namespace phonics_game
