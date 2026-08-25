#pragma once

#include <stdint.h>

namespace phonics_game {

// Bubble variety has its own RNG domain so it cannot perturb the curriculum or
// the creature-reward sequence. Immediate repeats are excluded while all four
// variants remain equally reachable over time.
class RewardAudioSelector {
 public:
  static constexpr uint8_t kBubbleCount = 4;

  explicit RewardAudioSelector(uint32_t seed) { reset(seed); }

  void reset(uint32_t seed) {
    state_ = seed == 0 ? 0x9e3779b9u : seed;
    previous_ = 0;
    hasPrevious_ = false;
  }

  uint8_t nextBubble() {
    uint8_t selected = bounded(next(), hasPrevious_ ? kBubbleCount - 1
                                                    : kBubbleCount);
    if (hasPrevious_ && selected >= previous_) ++selected;
    previous_ = selected;
    hasPrevious_ = true;
    return selected;
  }

 private:
  static uint8_t bounded(uint32_t value, uint8_t upperExclusive) {
    return static_cast<uint8_t>(
        (static_cast<uint64_t>(value) * upperExclusive) >> 32);
  }

  uint32_t next() {
    uint32_t value = state_;
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    state_ = value;
    return value;
  }

  uint32_t state_ = 0;
  uint8_t previous_ = 0;
  bool hasPrevious_ = false;
};

}  // namespace phonics_game
