#include <assert.h>
#include <stdint.h>

#include "../firmware/PhonicsGame/GameEngine.h"

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
