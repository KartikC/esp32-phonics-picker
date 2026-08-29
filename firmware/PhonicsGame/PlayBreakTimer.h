#pragma once

#include <stdint.h>

namespace phonics_game {

constexpr uint32_t kPlayAllowanceMs = 10u * 60u * 1000u;
constexpr uint32_t kPlayBreakDurationMs = 30u * 60u * 1000u;

enum class PlayBreakState : uint8_t {
  playing,
  breakPending,
  onBreak,
};

enum class PlayBreakEvent : uint8_t {
  none,
  breakStarted,
  playResumed,
};

// Pure wrap-safe clock for the product's repeating play/rest cadence. Active
// play is accumulated only while the application leaves the clock resumed.
// Once a break begins, its deadline is elapsed wall time and deliberately does
// not pause with the display or the normal game state.
class PlayBreakTimer {
 public:
  PlayBreakEvent begin(uint32_t nowMs) {
    started_ = true;
    playPaused_ = false;
    breakDue_ = false;
    onBreak_ = false;
    activePlayMs_ = 0;
    lastPlayUpdateAtMs_ = nowMs;
    breakStartedAtMs_ = 0;
    return PlayBreakEvent::none;
  }

  PlayBreakEvent update(uint32_t nowMs, bool canStartBreak) {
    if (!started_) return PlayBreakEvent::none;

    if (onBreak_) {
      if (elapsed(nowMs, breakStartedAtMs_) < kPlayBreakDurationMs) {
        return PlayBreakEvent::none;
      }
      onBreak_ = false;
      breakDue_ = false;
      activePlayMs_ = 0;
      // The application creates and paints a fresh round before explicitly
      // resuming the next allowance, so no hidden time is consumed here.
      playPaused_ = true;
      lastPlayUpdateAtMs_ = nowMs;
      return PlayBreakEvent::playResumed;
    }

    if (!playPaused_) accumulatePlay(nowMs);
    if (activePlayMs_ >= kPlayAllowanceMs) breakDue_ = true;
    if (!breakDue_ || !canStartBreak) return PlayBreakEvent::none;

    breakDue_ = false;
    onBreak_ = true;
    playPaused_ = true;
    breakStartedAtMs_ = nowMs;
    return PlayBreakEvent::breakStarted;
  }

  void pausePlay(uint32_t nowMs) {
    if (!started_ || onBreak_ || playPaused_) return;
    accumulatePlay(nowMs);
    if (activePlayMs_ >= kPlayAllowanceMs) breakDue_ = true;
    playPaused_ = true;
  }

  void resumePlay(uint32_t nowMs) {
    if (!started_ || onBreak_ || !playPaused_) return;
    lastPlayUpdateAtMs_ = nowMs;
    playPaused_ = false;
  }

  PlayBreakState state() const {
    if (onBreak_) return PlayBreakState::onBreak;
    return breakDue_ ? PlayBreakState::breakPending :
                       PlayBreakState::playing;
  }

  bool playing() const { return started_ && !onBreak_; }
  bool breakPending() const { return breakDue_; }
  bool onBreak() const { return onBreak_; }
  bool playPaused() const { return playPaused_; }

  uint32_t activePlayMs() const { return activePlayMs_; }

  uint32_t playRemainingMs() const {
    if (onBreak_ || activePlayMs_ >= kPlayAllowanceMs) return 0;
    return kPlayAllowanceMs - activePlayMs_;
  }

  uint32_t playRemainingSeconds() const {
    return ceilSeconds(playRemainingMs());
  }

  uint32_t breakRemainingMs(uint32_t nowMs) const {
    if (!onBreak_) return 0;
    const uint32_t spent = elapsed(nowMs, breakStartedAtMs_);
    return spent >= kPlayBreakDurationMs ? 0 :
                                          kPlayBreakDurationMs - spent;
  }

  uint32_t breakRemainingSeconds(uint32_t nowMs) const {
    return ceilSeconds(breakRemainingMs(nowMs));
  }

 private:
  static uint32_t elapsed(uint32_t nowMs, uint32_t thenMs) {
    return nowMs - thenMs;
  }

  static uint32_t ceilSeconds(uint32_t milliseconds) {
    return milliseconds == 0 ? 0 : (milliseconds - 1u) / 1000u + 1u;
  }

  void accumulatePlay(uint32_t nowMs) {
    const uint32_t delta = elapsed(nowMs, lastPlayUpdateAtMs_);
    lastPlayUpdateAtMs_ = nowMs;
    const uint32_t remaining = activePlayMs_ >= kPlayAllowanceMs ? 0 :
        kPlayAllowanceMs - activePlayMs_;
    activePlayMs_ += delta >= remaining ? remaining : delta;
  }

  bool started_ = false;
  bool playPaused_ = true;
  bool breakDue_ = false;
  bool onBreak_ = false;
  uint32_t activePlayMs_ = 0;
  uint32_t lastPlayUpdateAtMs_ = 0;
  uint32_t breakStartedAtMs_ = 0;
};

}  // namespace phonics_game
