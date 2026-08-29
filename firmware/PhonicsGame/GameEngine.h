#pragma once

#include <stdint.h>

namespace phonics_game {

constexpr uint8_t kLetterCount = 26;
constexpr uint8_t kPromptVariantCount = 5;
constexpr uint8_t kNudgeVariantCount = 4;
// Only the neutral "No, no." cue fits a wrong answer that advances instead of
// inviting another try on the same challenge.
constexpr uint8_t kWrongVariantCount = 1;
constexpr uint8_t kPraiseVariantCount = 4;
constexpr uint8_t kLayoutVariantCount = 6;
constexpr uint32_t kFirstNudgeDelayMs = 8000;
constexpr uint32_t kSecondNudgeDelayMs = 10000;
// Freeze the answered round long enough for a cold audio wake plus the 830 ms
// neutral cue, then show a complete black beat before composing the next
// challenge. The black phase is timed from the frame that actually draws it,
// so a busy loop can delay but never skip the visual transition.
constexpr uint32_t kWrongFeedbackDurationMs = 1100;
constexpr uint32_t kWrongBlackBeatDurationMs = 120;
// A correct answer first confirms the chosen card, then transitions into a
// short underwater creature reward before returning to the next clean round.
constexpr uint32_t kCorrectPulseEndMs = 400;
constexpr uint32_t kWaterRiseEndMs = 640;
// Keep the creature on screen for a device-rounded 2520 ms (640..3160), 14.5%
// longer than the previous 2200 ms window. Only the full-water hold grows; the
// rise and recede keep their established pacing.
constexpr uint32_t kCreatureRewardEndMs = 2880;
constexpr uint32_t kWaterRecedeEndMs = 3160;
// Leave a deliberate fully black beat after the recede. At 120 ms it cannot
// be skipped by a single framebuffer composite/flush before the next round.
constexpr uint32_t kCelebrationDurationMs = 3280;

enum class EventType : uint8_t {
  none,
  roundStarted,
  nudge,
  wrongChoice,
  wrongBlackBeat,
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
    suspended_ = false;
    return beginRound(nowMs);
  }

  Event update(uint32_t nowMs) {
    if (!started_ || suspended_) return Event{};

    if (wrongFeedback_) {
      if (elapsed(nowMs, wrongTransitionStartedAtMs_) >=
          kWrongFeedbackDurationMs) {
        wrongFeedback_ = false;
        wrongBlackBeat_ = true;
        wrongTransitionStartedAtMs_ = nowMs;
        return Event{EventType::wrongBlackBeat, 0};
      }
      return Event{};
    }

    if (wrongBlackBeat_) {
      if (wrongBlackFramePresented_ &&
          elapsed(nowMs, wrongTransitionStartedAtMs_) >=
          kWrongBlackBeatDurationMs) {
        return beginRound(nowMs);
      }
      return Event{};
    }

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
    if (!acceptingInput()) return Event{};
    lastInteractionAtMs_ = nowMs;
    const bool correct = choseLeft == round_.targetOnLeft;
    if (!correct) {
      wrongFeedback_ = true;
      wrongTransitionStartedAtMs_ = nowMs;
      return Event{EventType::wrongChoice, random_.below(kWrongVariantCount)};
    }

    celebrating_ = true;
    celebrationStartedAtMs_ = nowMs;
    return Event{EventType::correctChoice, random_.below(kPraiseVariantCount)};
  }

  // Replay keeps the exact round and prompt, but counts as engagement so an
  // idle nudge never talks over the replayed instruction.
  bool replay(uint32_t nowMs) {
    if (!acceptingInput()) return false;
    lastInteractionAtMs_ = nowMs;
    return true;
  }

  // Start the black-beat clock only after the compositor confirms the complete
  // frame was flushed. Without this acknowledgement, fail closed on black
  // rather than exposing a too-short or skipped transition.
  void acknowledgeWrongBlackFrame(uint32_t nowMs) {
    if (!wrongBlackBeat_) return;
    wrongBlackFramePresented_ = true;
    wrongTransitionStartedAtMs_ = nowMs;
  }

  void suspend(uint32_t nowMs) {
    if (!started_ || suspended_) return;
    suspended_ = true;
    suspendedAtMs_ = nowMs;
  }

  void resume(uint32_t nowMs) {
    if (!suspended_) return;
    const uint32_t pausedMs = elapsed(nowMs, suspendedAtMs_);
    lastInteractionAtMs_ += pausedMs;
    if (celebrating_) celebrationStartedAtMs_ += pausedMs;
    if (wrongTransitioning()) wrongTransitionStartedAtMs_ += pausedMs;
    suspended_ = false;
  }

  const Round& round() const { return round_; }
  bool celebrating() const { return celebrating_; }
  bool wrongTransitioning() const {
    return wrongFeedback_ || wrongBlackBeat_;
  }
  bool wrongFeedback() const { return wrongFeedback_; }
  bool wrongBlackBeat() const { return wrongBlackBeat_; }
  bool transitioning() const { return celebrating_ || wrongTransitioning(); }
  bool acceptingInput() const {
    return started_ && !suspended_ && !transitioning();
  }
  bool suspended() const { return suspended_; }
  uint32_t celebrationElapsed(uint32_t nowMs) const {
    const uint32_t effectiveNow = suspended_ ? suspendedAtMs_ : nowMs;
    return celebrating_ ? elapsed(effectiveNow, celebrationStartedAtMs_) : 0;
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
    wrongFeedback_ = false;
    wrongBlackBeat_ = false;
    wrongBlackFramePresented_ = false;
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
  bool wrongFeedback_ = false;
  bool wrongBlackBeat_ = false;
  bool wrongBlackFramePresented_ = false;
  bool suspended_ = false;
  bool hasPreviousTarget_ = false;
  uint8_t previousTarget_ = 0;
  uint8_t nudgeLevel_ = 0;
  uint8_t lastPromptVariant_ = 0xff;
  uint8_t lastNudgeVariant_ = 0xff;
  uint32_t lastInteractionAtMs_ = 0;
  uint32_t celebrationStartedAtMs_ = 0;
  uint32_t wrongTransitionStartedAtMs_ = 0;
  uint32_t suspendedAtMs_ = 0;
};

}  // namespace phonics_game
