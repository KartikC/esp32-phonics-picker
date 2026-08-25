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
  assert(wrongGame.round().target == original.target);
  assert(wrongGame.round().distractor == original.distractor);
  assert(wrongGame.update(600 + kFirstNudgeDelayMs - 1).type == EventType::none);
  assert(wrongGame.update(600 + kFirstNudgeDelayMs).type == EventType::nudge);

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
  constexpr uint32_t kPreviousCreatureOnScreenMs = 1840;
  constexpr uint32_t kCreatureOnScreenMs =
      kWaterRecedeEndMs - kWaterRiseEndMs;
  static_assert(kCreatureOnScreenMs == 2200,
                "the creature should now remain on screen for 2200 ms");
  static_assert(kCreatureOnScreenMs * 100 >=
                    kPreviousCreatureOnScreenMs * 118 &&
                kCreatureOnScreenMs * 100 <=
                    kPreviousCreatureOnScreenMs * 122,
                "the creature window should grow by approximately 20 percent");

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
