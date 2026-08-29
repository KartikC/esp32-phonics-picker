#include <cassert>
#include <cstdint>
#include <iostream>

#include "../firmware/PhonicsGame/GameEngine.h"
#include "../firmware/PhonicsGame/PlayBreakTimer.h"

using namespace phonics_game;

int main() {
  static_assert(kPlayAllowanceMs == 600000u);
  static_assert(kPlayBreakDurationMs == 1800000u);

  PlayBreakTimer timer;
  assert(timer.begin(100) == PlayBreakEvent::none);
  assert(timer.state() == PlayBreakState::playing);
  assert(timer.playRemainingSeconds() == 600);
  assert(timer.update(100 + kPlayAllowanceMs - 1, true) ==
         PlayBreakEvent::none);
  assert(timer.playRemainingMs() == 1);
  assert(timer.playRemainingSeconds() == 1);
  assert(timer.update(100 + kPlayAllowanceMs, true) ==
         PlayBreakEvent::breakStarted);
  assert(timer.state() == PlayBreakState::onBreak);
  assert(timer.breakRemainingSeconds(100 + kPlayAllowanceMs) == 1800);
  assert(timer.breakRemainingSeconds(100 + kPlayAllowanceMs + 1) == 1800);
  assert(timer.breakRemainingSeconds(100 + kPlayAllowanceMs + 1000) == 1799);
  assert(timer.breakRemainingSeconds(
             100 + kPlayAllowanceMs + kPlayBreakDurationMs - 1) == 1);
  assert(timer.update(
             100 + kPlayAllowanceMs + kPlayBreakDurationMs - 1, true) ==
         PlayBreakEvent::none);
  assert(timer.update(
             100 + kPlayAllowanceMs + kPlayBreakDurationMs, true) ==
         PlayBreakEvent::playResumed);
  assert(timer.state() == PlayBreakState::playing);
  assert(timer.playPaused());
  assert(timer.playRemainingSeconds() == 600);

  // The next allowance begins only when the application has installed the
  // fresh round and explicitly resumes the play clock.
  const uint32_t secondSessionAt =
      100 + kPlayAllowanceMs + kPlayBreakDurationMs;
  timer.resumePlay(secondSessionAt + 5000);
  assert(!timer.playPaused());
  assert(timer.update(secondSessionAt + 5000 + kPlayAllowanceMs, true) ==
         PlayBreakEvent::breakStarted);

  // Standby and USB preview pause active play, including repeated/idempotent
  // pause calls, while an established break continues against wall time.
  PlayBreakTimer paused;
  paused.begin(1000);
  assert(paused.update(301000, true) == PlayBreakEvent::none);
  paused.pausePlay(301000);
  paused.pausePlay(401000);
  assert(paused.activePlayMs() == 300000);
  assert(paused.update(901000, true) == PlayBreakEvent::none);
  paused.resumePlay(901000);
  paused.resumePlay(1001000);
  assert(paused.update(1201000 - 1, true) == PlayBreakEvent::none);
  assert(paused.update(1201000, true) == PlayBreakEvent::breakStarted);
  paused.pausePlay(1202000);
  assert(paused.breakRemainingSeconds(2101000) == 900);
  assert(paused.update(3001000, true) == PlayBreakEvent::playResumed);

  // A boundary reached during answer feedback becomes pending. Delayed loops
  // may extend that feedback but can never consume the 30-minute rest period
  // before the application actually paints the timer.
  PlayBreakTimer pending;
  pending.begin(50);
  assert(pending.update(50 + kPlayAllowanceMs, false) ==
         PlayBreakEvent::none);
  assert(pending.state() == PlayBreakState::breakPending);
  assert(pending.playRemainingSeconds() == 0);
  assert(pending.update(50 + kPlayAllowanceMs + 3280, false) ==
         PlayBreakEvent::none);
  assert(pending.update(50 + kPlayAllowanceMs + 9000, true) ==
         PlayBreakEvent::breakStarted);
  assert(pending.breakRemainingSeconds(50 + kPlayAllowanceMs + 9000) ==
         1800);

  // Unsigned subtraction keeps both boundaries correct across millis() wrap.
  constexpr uint32_t nearWrap = UINT32_MAX - 2000u;
  PlayBreakTimer wrapping;
  wrapping.begin(nearWrap);
  const uint32_t wrappedBreakStart = nearWrap + kPlayAllowanceMs;
  assert(wrapping.update(wrappedBreakStart - 1u, true) ==
         PlayBreakEvent::none);
  assert(wrapping.update(wrappedBreakStart, true) ==
         PlayBreakEvent::breakStarted);
  assert(wrapping.breakRemainingSeconds(wrappedBreakStart) == 1800);
  assert(wrapping.update(wrappedBreakStart + kPlayBreakDurationMs, true) ==
         PlayBreakEvent::playResumed);

  // If a wrong-answer transition creates its next round on the exact limit,
  // that already-selected event is the post-break challenge. Generating once
  // more at resume could choose the answered target again.
  GameEngine boundaryGame(0xBEEFu);
  PlayBreakTimer boundaryTimer;
  const Event answeredRound = boundaryGame.begin(0);
  assert(answeredRound.type == EventType::roundStarted);
  const uint8_t answeredTarget = boundaryGame.round().target;
  boundaryTimer.begin(0);
  constexpr uint32_t wrongAt =
      kPlayAllowanceMs - kWrongFeedbackDurationMs - kWrongBlackBeatDurationMs;
  assert(boundaryTimer.update(wrongAt, false) == PlayBreakEvent::none);
  assert(boundaryGame.choose(!boundaryGame.round().targetOnLeft, wrongAt).type ==
         EventType::wrongChoice);
  const uint32_t blackAt = wrongAt + kWrongFeedbackDurationMs;
  const Event black = boundaryGame.update(blackAt);
  assert(black.type == EventType::wrongBlackBeat);
  boundaryGame.acknowledgeWrongBlackFrame(blackAt);
  assert(boundaryTimer.update(blackAt, false) == PlayBreakEvent::none);
  const Event deferredRound = boundaryGame.update(kPlayAllowanceMs);
  assert(deferredRound.type == EventType::roundStarted);
  const uint8_t deferredTarget = boundaryGame.round().target;
  assert(deferredTarget != answeredTarget);
  assert(boundaryTimer.update(kPlayAllowanceMs,
                              !boundaryGame.transitioning()) ==
         PlayBreakEvent::breakStarted);
  boundaryGame.suspend(kPlayAllowanceMs);
  assert(boundaryTimer.update(kPlayAllowanceMs + kPlayBreakDurationMs, true) ==
         PlayBreakEvent::playResumed);
  boundaryGame.resume(kPlayAllowanceMs + kPlayBreakDurationMs);
  boundaryTimer.resumePlay(kPlayAllowanceMs + kPlayBreakDurationMs);
  assert(boundaryGame.round().target == deferredTarget);
  assert(deferredRound.variant == boundaryGame.round().promptVariant);

  // The same deferred-round rule applies when a complete correct reward ends
  // on the boundary rather than the shorter wrong-answer transition.
  GameEngine rewardBoundaryGame(0xCAFEu);
  PlayBreakTimer rewardBoundaryTimer;
  assert(rewardBoundaryGame.begin(0).type == EventType::roundStarted);
  const uint8_t rewardedTarget = rewardBoundaryGame.round().target;
  rewardBoundaryTimer.begin(0);
  constexpr uint32_t correctAt =
      kPlayAllowanceMs - kCelebrationDurationMs;
  assert(rewardBoundaryTimer.update(correctAt, false) == PlayBreakEvent::none);
  assert(rewardBoundaryGame.choose(
             rewardBoundaryGame.round().targetOnLeft, correctAt).type ==
         EventType::correctChoice);
  const Event rewardDeferredRound =
      rewardBoundaryGame.update(kPlayAllowanceMs);
  assert(rewardDeferredRound.type == EventType::roundStarted);
  assert(rewardBoundaryGame.round().target != rewardedTarget);
  assert(rewardBoundaryTimer.update(
             kPlayAllowanceMs, !rewardBoundaryGame.transitioning()) ==
         PlayBreakEvent::breakStarted);

  std::cout << "play break timer contract passed\n";
  return 0;
}
