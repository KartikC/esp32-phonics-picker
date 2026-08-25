#pragma once

#include <stdint.h>

#include "GameEngine.h"

namespace phonics_game {

struct CardRect {
  int16_t x;
  int16_t y;
  int16_t w;
  int16_t h;
};

struct LayoutOffset {
  int8_t leftX;
  int8_t leftY;
  int8_t rightX;
  int8_t rightY;
};

inline constexpr LayoutOffset kLayoutOffsets[kLayoutVariantCount] = {
    {0, 0, 0, 6}, {-7, 7, 5, -2}, {5, -4, -7, 7},
    {-3, -6, 7, 3}, {7, 4, -4, -5}, {-5, 2, 4, 8},
};

constexpr int16_t kScreenWidth = 368;
constexpr int16_t kScreenHeight = 448;
constexpr int16_t kCardWidth = 138;
constexpr int16_t kCardHeight = 158;
constexpr int16_t kLeftCardBaseX = 32;
constexpr int16_t kRightCardBaseX = 195;
constexpr int16_t kCardBaseY = 206;
constexpr int16_t kMaxTileSlideX = 19;
constexpr int16_t kMaxTileSlideY = 44;
constexpr int16_t kMinHorizontalSlideSeparation = -2;
constexpr int16_t kMaxHorizontalSlideSeparation = 6;
constexpr int16_t kMaxVerticalSlideSeparation = 8;
constexpr int16_t kMaxCelebrationPulse = 6;
constexpr int16_t kCardShadowX = 3;
constexpr int16_t kCardShadowY = 6;
constexpr int16_t kReplayCenterX = kScreenWidth / 2;
constexpr int16_t kReplayCenterY = 60;
constexpr int16_t kReplayVisualRadius = 32;
constexpr int16_t kReplayHitRadius = 42;

constexpr CardRect makeCardRect(bool left, uint8_t layoutVariant,
                                int16_t slideX, int16_t slideY,
                                int16_t pulse = 0) {
  const LayoutOffset& offset = kLayoutOffsets[layoutVariant];
  const int16_t baseX = left ? kLeftCardBaseX : kRightCardBaseX;
  const int16_t xOffset = left ? offset.leftX : offset.rightX;
  const int16_t yOffset = left ? offset.leftY : offset.rightY;
  return CardRect{static_cast<int16_t>(baseX + xOffset + slideX - pulse),
                  static_cast<int16_t>(kCardBaseY + yOffset + slideY - pulse),
                  static_cast<int16_t>(kCardWidth + pulse * 2),
                  static_cast<int16_t>(kCardHeight + pulse * 2)};
}

// These prove the extreme motion/pulse envelopes, including the three-by-six
// pixel shadow, remain inside the panel and clear of the fixed replay target.
static_assert(kLeftCardBaseX - 7 - kMaxTileSlideX - kMaxCelebrationPulse >= 0,
              "left tile can leave the display");
static_assert(kRightCardBaseX + 7 + kMaxTileSlideX - kMaxCelebrationPulse +
                      kCardShadowX + kCardWidth + 2 * kMaxCelebrationPulse <=
                  kScreenWidth,
              "right tile shadow can leave the display");
static_assert(kCardBaseY - 6 - kMaxTileSlideY - kMaxCelebrationPulse >
                  kReplayCenterY + kReplayHitRadius,
              "tile can collide with replay target");
static_assert(kCardBaseY + 8 + kMaxTileSlideY - kMaxCelebrationPulse +
                      kCardShadowY + kCardHeight + 2 * kMaxCelebrationPulse <=
                  kScreenHeight,
              "tile shadow can leave the display");
constexpr int16_t minimumBaseCardGap() {
  int16_t minimum = kScreenWidth;
  for (const LayoutOffset& offset : kLayoutOffsets) {
    const int16_t gap = kRightCardBaseX + offset.rightX -
                        (kLeftCardBaseX + offset.leftX + kCardWidth +
                         kCardShadowX);
    if (gap < minimum) minimum = gap;
  }
  return minimum;
}

static_assert(minimumBaseCardGap() - kMaxCelebrationPulse +
                      kMinHorizontalSlideSeparation >= 2,
              "tile shadows can overlap");

}  // namespace phonics_game
