#include <assert.h>
#include <stdint.h>

#include "../firmware/PhonicsGame/GameEngine.h"
#include "../firmware/PhonicsGame/LayoutGeometry.h"

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
  assert(pausedCelebrationGame.update(11299).type == EventType::none);
  assert(pausedCelebrationGame.update(11300).type == EventType::roundStarted);

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
