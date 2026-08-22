#pragma once

#include <stdint.h>

namespace phonics_game {

constexpr uint8_t kLetterCount = 26;
constexpr uint8_t kPromptVariantCount = 5;
constexpr uint8_t kNudgeVariantCount = 4;
constexpr uint8_t kWrongVariantCount = 3;
constexpr uint8_t kPraiseVariantCount = 4;
constexpr uint8_t kLayoutVariantCount = 6;
constexpr uint32_t kFirstNudgeDelayMs = 8000;
constexpr uint32_t kSecondNudgeDelayMs = 10000;
constexpr uint32_t kCelebrationDurationMs = 1100;

enum class EventType : uint8_t {
  none,
  roundStarted,
  nudge,
  wrongChoice,
  correctChoice,
};

struct Event {
  EventType type = EventType::none;
  uint8_t variant = 0;
};

struct Round {
  uint8_t target = 0;
  uint8_t distractor = 1;
  bool targetOnLeft = true;
  uint8_t layoutVariant = 0;
  uint8_t promptVariant = 0;
};

class RandomSource {
 public:
  explicit RandomSource(uint32_t seed) : state_(seed == 0 ? 0x6d2b79f5u : seed) {}

  uint32_t next() {
    uint32_t value = state_;
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    state_ = value;
    return value;
  }

  uint8_t below(uint8_t upperExclusive) {
    return static_cast<uint8_t>(next() % upperExclusive);
  }

 private:
  uint32_t state_;
};

class GameEngine {
 public:
  explicit GameEngine(uint32_t seed) : random_(seed) {}

  Event begin(uint32_t nowMs) {
    started_ = true;
    return beginRound(nowMs);
  }

  Event update(uint32_t nowMs) {
    if (!started_) return Event{};

    if (celebrating_) {
      if (elapsed(nowMs, celebrationStartedAtMs_) >= kCelebrationDurationMs) {
        return beginRound(nowMs);
      }
      return Event{};
    }

    const uint32_t idleMs = elapsed(nowMs, lastInteractionAtMs_);
    if (nudgeLevel_ == 0 && idleMs >= kFirstNudgeDelayMs) {
      nudgeLevel_ = 1;
      lastInteractionAtMs_ = nowMs;
      return Event{EventType::nudge, chooseDifferent(kNudgeVariantCount, lastNudgeVariant_)};
    }
    if (nudgeLevel_ == 1 && idleMs >= kSecondNudgeDelayMs) {
      nudgeLevel_ = 2;
      lastInteractionAtMs_ = nowMs;
      return Event{EventType::nudge, chooseDifferent(kNudgeVariantCount, lastNudgeVariant_)};
    }
    return Event{};
  }

  Event choose(bool choseLeft, uint32_t nowMs) {
    if (!started_ || celebrating_) return Event{};
    lastInteractionAtMs_ = nowMs;
    const bool correct = choseLeft == round_.targetOnLeft;
    if (!correct) {
      return Event{EventType::wrongChoice, random_.below(kWrongVariantCount)};
    }

    celebrating_ = true;
    celebrationStartedAtMs_ = nowMs;
    return Event{EventType::correctChoice, random_.below(kPraiseVariantCount)};
  }

  const Round& round() const { return round_; }
  bool celebrating() const { return celebrating_; }
  uint32_t celebrationElapsed(uint32_t nowMs) const {
    return celebrating_ ? elapsed(nowMs, celebrationStartedAtMs_) : 0;
  }
  uint8_t nudgeLevel() const { return nudgeLevel_; }

  static char letter(uint8_t index) { return static_cast<char>('a' + index); }

  static bool indistinguishablePair(uint8_t first, uint8_t second) {
    constexpr uint8_t c = static_cast<uint8_t>('c' - 'a');
    constexpr uint8_t k = static_cast<uint8_t>('k' - 'a');
    return (first == c && second == k) || (first == k && second == c);
  }

 private:
  static uint32_t elapsed(uint32_t nowMs, uint32_t thenMs) {
    return nowMs - thenMs;
  }

  uint8_t chooseDifferent(uint8_t count, uint8_t& previous) {
    uint8_t value = random_.below(count);
    if (count > 1 && value == previous) value = static_cast<uint8_t>((value + 1) % count);
    previous = value;
    return value;
  }

  Event beginRound(uint32_t nowMs) {
    celebrating_ = false;
    nudgeLevel_ = 0;
    lastInteractionAtMs_ = nowMs;

    uint8_t nextTarget = random_.below(kLetterCount);
    if (hasPreviousTarget_ && nextTarget == previousTarget_) {
      nextTarget = static_cast<uint8_t>((nextTarget + 1 + random_.below(kLetterCount - 1)) % kLetterCount);
    }
    round_.target = nextTarget;
    previousTarget_ = nextTarget;
    hasPreviousTarget_ = true;

    do {
      round_.distractor = random_.below(kLetterCount);
    } while (round_.distractor == round_.target ||
             indistinguishablePair(round_.target, round_.distractor));

    round_.targetOnLeft = random_.below(2) == 0;
    round_.layoutVariant = random_.below(kLayoutVariantCount);
    round_.promptVariant = chooseDifferent(kPromptVariantCount, lastPromptVariant_);
    return Event{EventType::roundStarted, round_.promptVariant};
  }

  RandomSource random_;
  Round round_;
  bool started_ = false;
  bool celebrating_ = false;
  bool hasPreviousTarget_ = false;
  uint8_t previousTarget_ = 0;
  uint8_t nudgeLevel_ = 0;
  uint8_t lastPromptVariant_ = 0xff;
  uint8_t lastNudgeVariant_ = 0xff;
  uint32_t lastInteractionAtMs_ = 0;
  uint32_t celebrationStartedAtMs_ = 0;
};

}  // namespace phonics_game
