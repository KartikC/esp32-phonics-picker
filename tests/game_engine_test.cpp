#include <assert.h>
#include <stdint.h>

#include "../firmware/PhonicsGame/GameEngine.h"
#include "../firmware/PhonicsGame/LayoutGeometry.h"
#include "../firmware/PhonicsGame/RewardTransition.h"

using namespace phonics_game;

int main() {
  GameEngine game(0x12345678);
  Event event = game.begin(100);
  assert(event.type == EventType::roundStarted);

  uint8_t previousTarget = game.round().target;
  bool sawLeft = game.round().targetOnLeft;
  bool sawRight = !game.round().targetOnLeft;
  bool sawLayout[kLayoutVariantCount] = {};
  bool sawPrompt[kPromptVariantCount] = {};
  sawLayout[game.round().layoutVariant] = true;
  sawPrompt[game.round().promptVariant] = true;

  uint32_t now = 100;
  for (int round = 0; round < 250; ++round) {
    assert(game.round().target != game.round().distractor);
    assert(!GameEngine::indistinguishablePair(game.round().target, game.round().distractor));
    assert(game.round().target != previousTarget || round == 0);

    event = game.choose(game.round().targetOnLeft, now);
    assert(event.type == EventType::correctChoice);
    assert(game.update(now + kCelebrationDurationMs - 1).type == EventType::none);
    previousTarget = game.round().target;
    now += kCelebrationDurationMs;
    event = game.update(now);
    assert(event.type == EventType::roundStarted);
    sawLeft |= game.round().targetOnLeft;
    sawRight |= !game.round().targetOnLeft;
    sawLayout[game.round().layoutVariant] = true;
    sawPrompt[game.round().promptVariant] = true;
  }
  assert(sawLeft && sawRight);
  for (bool seen : sawLayout) assert(seen);
  for (bool seen : sawPrompt) assert(seen);

  GameEngine idleGame(9);
  idleGame.begin(1000);
  assert(idleGame.update(1000 + kFirstNudgeDelayMs - 1).type == EventType::none);
  event = idleGame.update(1000 + kFirstNudgeDelayMs);
  assert(event.type == EventType::nudge);
  assert(idleGame.nudgeLevel() == 1);
  assert(idleGame.update(1000 + kFirstNudgeDelayMs + kSecondNudgeDelayMs - 1).type == EventType::none);
  event = idleGame.update(1000 + kFirstNudgeDelayMs + kSecondNudgeDelayMs);
  assert(event.type == EventType::nudge);
  assert(idleGame.nudgeLevel() == 2);
  assert(idleGame.update(UINT32_MAX).type == EventType::none);

  GameEngine wrongGame(77);
  wrongGame.begin(500);
  const Round original = wrongGame.round();
  event = wrongGame.choose(!original.targetOnLeft, 600);
  assert(event.type == EventType::wrongChoice);
  assert(event.variant == 0);
  assert(wrongGame.wrongFeedback());
  assert(wrongGame.transitioning());
  assert(!wrongGame.acceptingInput());
  assert(wrongGame.round().target == original.target);
  assert(wrongGame.round().distractor == original.distractor);
  assert(wrongGame.choose(original.targetOnLeft, 700).type == EventType::none);
  assert(!wrongGame.replay(700));
  assert(wrongGame.update(600 + kWrongFeedbackDurationMs - 1).type ==
         EventType::none);
  event = wrongGame.update(600 + kWrongFeedbackDurationMs);
  assert(event.type == EventType::wrongBlackBeat);
  assert(wrongGame.wrongBlackBeat());
  assert(wrongGame.round().target == original.target);
  const uint32_t wrongBlackPresentedAt =
      600 + kWrongFeedbackDurationMs + 1000;
  assert(wrongGame.update(wrongBlackPresentedAt).type == EventType::none);
  wrongGame.acknowledgeWrongBlackFrame(wrongBlackPresentedAt);
  assert(wrongGame.update(wrongBlackPresentedAt +
                          kWrongBlackBeatDurationMs - 1).type ==
         EventType::none);
  const uint32_t wrongRoundStartedAt =
      wrongBlackPresentedAt + kWrongBlackBeatDurationMs;
  event = wrongGame.update(wrongRoundStartedAt);
  assert(event.type == EventType::roundStarted);
  assert(!wrongGame.transitioning());
  assert(wrongGame.acceptingInput());
  assert(wrongGame.round().target != original.target);
  assert(wrongGame.update(wrongRoundStartedAt + kFirstNudgeDelayMs - 1).type ==
         EventType::none);
  assert(wrongGame.update(wrongRoundStartedAt + kFirstNudgeDelayMs).type ==
         EventType::nudge);

  // A delayed loop may postpone the black frame, but it must still preserve a
  // complete black beat instead of jumping directly to the fresh round.
  GameEngine stalledWrongGame(78);
  stalledWrongGame.begin(0);
  assert(stalledWrongGame.choose(
             !stalledWrongGame.round().targetOnLeft, 10).type ==
         EventType::wrongChoice);
  event = stalledWrongGame.update(5000);
  assert(event.type == EventType::wrongBlackBeat);
  stalledWrongGame.acknowledgeWrongBlackFrame(5000);
  assert(stalledWrongGame.update(5000 + kWrongBlackBeatDurationMs - 1).type ==
         EventType::none);
  assert(stalledWrongGame.update(5000 + kWrongBlackBeatDurationMs).type ==
         EventType::roundStarted);

  GameEngine replayGame(81);
  replayGame.begin(1000);
  const Round replayRound = replayGame.round();
  assert(replayGame.update(1000 + kFirstNudgeDelayMs - 1).type == EventType::none);
  assert(replayGame.replay(1000 + kFirstNudgeDelayMs - 1));
  assert(replayGame.round().target == replayRound.target);
  assert(replayGame.round().distractor == replayRound.distractor);
  assert(replayGame.round().targetOnLeft == replayRound.targetOnLeft);
  assert(replayGame.round().promptVariant == replayRound.promptVariant);
  assert(replayGame.update(1000 + 2 * kFirstNudgeDelayMs - 2).type == EventType::none);
  assert(replayGame.update(1000 + 2 * kFirstNudgeDelayMs - 1).type == EventType::nudge);

  GameEngine pausedIdleGame(91);
  pausedIdleGame.begin(1000);
  pausedIdleGame.suspend(5000);
  assert(pausedIdleGame.suspended());
  assert(pausedIdleGame.update(UINT32_MAX).type == EventType::none);
  assert(!pausedIdleGame.replay(6000));
  assert(pausedIdleGame.choose(pausedIdleGame.round().targetOnLeft, 6000).type ==
         EventType::none);
  pausedIdleGame.resume(25000);
  assert(!pausedIdleGame.suspended());
  assert(pausedIdleGame.update(29000 - 1).type == EventType::none);
  assert(pausedIdleGame.update(29000).type == EventType::nudge);

  GameEngine pausedCelebrationGame(92);
  pausedCelebrationGame.begin(100);
  assert(pausedCelebrationGame.choose(
             pausedCelebrationGame.round().targetOnLeft, 200).type ==
         EventType::correctChoice);
  pausedCelebrationGame.suspend(500);
  assert(pausedCelebrationGame.celebrationElapsed(90000) == 300);
  pausedCelebrationGame.resume(10500);
  const uint32_t resumedCelebrationEnd =
      10500 + (kCelebrationDurationMs - 300);
  assert(pausedCelebrationGame.update(resumedCelebrationEnd - 1).type ==
         EventType::none);
  assert(pausedCelebrationGame.update(resumedCelebrationEnd).type ==
         EventType::roundStarted);

  GameEngine pausedWrongGame(93);
  pausedWrongGame.begin(100);
  assert(pausedWrongGame.choose(
             !pausedWrongGame.round().targetOnLeft, 200).type ==
         EventType::wrongChoice);
  pausedWrongGame.suspend(500);
  assert(pausedWrongGame.suspended());
  pausedWrongGame.resume(10500);
  const uint32_t resumedWrongFeedbackEnd =
      10500 + (kWrongFeedbackDurationMs - 300);
  assert(pausedWrongGame.update(resumedWrongFeedbackEnd - 1).type ==
         EventType::none);
  assert(pausedWrongGame.update(resumedWrongFeedbackEnd).type ==
         EventType::wrongBlackBeat);
  pausedWrongGame.acknowledgeWrongBlackFrame(resumedWrongFeedbackEnd);
  pausedWrongGame.suspend(resumedWrongFeedbackEnd + 40);
  pausedWrongGame.resume(resumedWrongFeedbackEnd + 5040);
  const uint32_t resumedWrongBlackEnd =
      resumedWrongFeedbackEnd + 5040 +
      (kWrongBlackBeatDurationMs - 40);
  assert(pausedWrongGame.update(resumedWrongBlackEnd - 1).type ==
         EventType::none);
  assert(pausedWrongGame.update(resumedWrongBlackEnd).type ==
         EventType::roundStarted);

  static_assert(kCorrectPulseEndMs < kWaterRiseEndMs,
                "the water transition must follow card confirmation");
  static_assert(kWaterRiseEndMs < kCreatureRewardEndMs,
                "the creature needs a visible reward hold");
  static_assert(kCreatureRewardEndMs < kCelebrationDurationMs,
                "the water needs time to recede before the next round");
  static_assert(kCreatureRewardEndMs < kWaterRecedeEndMs,
                "water recede must follow the creature hold");
  static_assert(kWaterRecedeEndMs < kCelebrationDurationMs,
                "a fully black frame must precede the next round");
  static_assert(kCelebrationDurationMs - kWaterRecedeEndMs >= 80,
                "the terminal black frame needs a reliable flush window");
  static_assert(kWaterRiseEndMs - kCorrectPulseEndMs == 240,
                "the established water-rise pacing must stay unchanged");
  static_assert(kWaterRecedeEndMs - kCreatureRewardEndMs == 280,
                "the established water-recede pacing must stay unchanged");
  static_assert(kCelebrationDurationMs - kWaterRecedeEndMs == 120,
                "the terminal black beat must remain 120 ms");
  static_assert(kWrongBlackBeatDurationMs == 120,
                "wrong advancement uses the same proven black beat");
  constexpr uint32_t kPreviousCreatureOnScreenMs = 2200;
  constexpr uint32_t kCreatureOnScreenMs =
      kWaterRecedeEndMs - kWaterRiseEndMs;
  static_assert(kCreatureOnScreenMs == 2520,
                "the creature should now remain on screen for 2520 ms");
  static_assert(kCreatureOnScreenMs * 100 >=
                    kPreviousCreatureOnScreenMs * 114 &&
                kCreatureOnScreenMs * 100 <=
                    kPreviousCreatureOnScreenMs * 116,
                "the creature window should grow by approximately 15 percent");

  constexpr uint16_t kTestDisplayHeight = 450;
  assert(!rewardCreatureVisible(kWaterRiseEndMs - 1));
  assert(rewardCreatureVisible(kWaterRiseEndMs));
  assert(rewardCreatureVisible(kCreatureRewardEndMs - 1));
  assert(rewardCreatureVisible(kCreatureRewardEndMs));
  assert(rewardCreatureVisible(kWaterRecedeEndMs - 1));
  assert(!rewardCreatureVisible(kWaterRecedeEndMs));
  assert(!rewardCreatureVisible(kCelebrationDurationMs));
  assert(rewardWaterSurfaceY(kCorrectPulseEndMs - 1,
                            kTestDisplayHeight) == kTestDisplayHeight);
  assert(rewardWaterSurfaceY(kCorrectPulseEndMs,
                            kTestDisplayHeight) == kTestDisplayHeight);
  assert(rewardWaterSurfaceY(kWaterRiseEndMs - 1,
                            kTestDisplayHeight) > 0);
  assert(rewardWaterSurfaceY(kWaterRiseEndMs,
                            kTestDisplayHeight) == 0);
  assert(rewardWaterSurfaceY(kCreatureRewardEndMs - 1,
                            kTestDisplayHeight) == 0);
  assert(rewardWaterSurfaceY(kCreatureRewardEndMs,
                            kTestDisplayHeight) == 0);
  assert(rewardWaterSurfaceY(kWaterRecedeEndMs - 1,
                            kTestDisplayHeight) < kTestDisplayHeight);
  assert(rewardWaterSurfaceY(kWaterRecedeEndMs,
                            kTestDisplayHeight) == kTestDisplayHeight);
  assert(rewardWaterSurfaceY(kCelebrationDurationMs,
                            kTestDisplayHeight) == kTestDisplayHeight);

  // Exhaust every independent horizontal pair allowed by the motion clamp,
  // both vertical extremes, and every celebration pulse. The shadow is
  // included because it is part of the visible tile envelope.
  constexpr int16_t verticalExtremes[] = {
      static_cast<int16_t>(-kMaxTileSlideY), kMaxTileSlideY};
  for (uint8_t layout = 0; layout < kLayoutVariantCount; ++layout) {
    for (int16_t leftX = -kMaxTileSlideX;
         leftX <= kMaxTileSlideX; ++leftX) {
      for (int16_t rightX = -kMaxTileSlideX;
           rightX <= kMaxTileSlideX; ++rightX) {
        const int16_t horizontalSeparation = rightX - leftX;
        if (horizontalSeparation < kMinHorizontalSlideSeparation ||
            horizontalSeparation > kMaxHorizontalSlideSeparation) continue;
        for (int16_t leftY : verticalExtremes) {
          for (int16_t verticalSeparation = -kMaxVerticalSlideSeparation;
               verticalSeparation <= kMaxVerticalSlideSeparation;
               ++verticalSeparation) {
            const int16_t rightY = leftY + verticalSeparation;
            if (rightY < -kMaxTileSlideY || rightY > kMaxTileSlideY) continue;
            for (int16_t pulse = 0; pulse <= kMaxCelebrationPulse; ++pulse) {
              for (uint8_t pulsedSide = 0; pulsedSide < 2; ++pulsedSide) {
                const CardRect left = makeCardRect(
                    true, layout, leftX, leftY,
                    pulsedSide == 0 ? pulse : 0);
                const CardRect right = makeCardRect(
                    false, layout, rightX, rightY,
                    pulsedSide == 1 ? pulse : 0);
                assert(left.x >= 0 && left.y >= 0);
                assert(right.x >= 0 && right.y >= 0);
                assert(left.x + left.w + kCardShadowX <= kScreenWidth);
                assert(right.x + right.w + kCardShadowX <= kScreenWidth);
                assert(left.y + left.h + kCardShadowY <= kScreenHeight);
                assert(right.y + right.h + kCardShadowY <= kScreenHeight);
                assert(left.x + left.w + kCardShadowX <= right.x);
                assert(left.y > kReplayCenterY + kReplayHitRadius);
                assert(right.y > kReplayCenterY + kReplayHitRadius);
              }
            }
          }
        }
      }
    }
  }

  // Two-choice integrity across many independent RNG streams and rounds.
  for (uint32_t seed = 1; seed <= 512; ++seed) {
    GameEngine integrityGame(seed);
    uint32_t integrityNow = 0;
    integrityGame.begin(integrityNow);
    for (int round = 0; round < 256; ++round) {
      assert(integrityGame.round().target != integrityGame.round().distractor);
      assert(!GameEngine::indistinguishablePair(
          integrityGame.round().target, integrityGame.round().distractor));
      assert(integrityGame.choose(integrityGame.round().targetOnLeft,
                                  integrityNow).type == EventType::correctChoice);
      integrityNow += kCelebrationDurationMs;
      assert(integrityGame.update(integrityNow).type == EventType::roundStarted);
    }
  }

  return 0;
}
