#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../firmware/PhonicsGame/AudioPlan.h"
#include "../firmware/PhonicsGame/RewardAudioSelector.h"

using phonics_game::AudioPlan;
using phonics_game::RewardAudioSelector;

int main() {
  static_assert(RewardAudioSelector::kBubbleCount == 4,
                "the accepted reward set has four bubble variants");

  RewardAudioSelector first(0x12345678u);
  RewardAudioSelector second(0x12345678u);
  bool seen[RewardAudioSelector::kBubbleCount] = {};
  uint8_t previous = first.nextBubble();
  assert(previous == second.nextBubble());
  seen[previous] = true;
  for (uint16_t draw = 1; draw < 512; ++draw) {
    const uint8_t selected = first.nextBubble();
    assert(selected == second.nextBubble());
    assert(selected < RewardAudioSelector::kBubbleCount);
    assert(selected != previous);
    seen[selected] = true;
    previous = selected;
  }
  for (bool wasSeen : seen) assert(wasSeen);

  RewardAudioSelector zeroSeed(0);
  assert(zeroSeed.nextBubble() < RewardAudioSelector::kBubbleCount);

  const char* praises[] = {
      "praise_nice_job", "praise_great_work",
      "praise_you_got_it", "praise_thats_it",
  };
  for (uint8_t bubble = 0; bubble < 4; ++bubble) {
    for (uint8_t creature = 0; creature < 8; ++creature) {
      char expectedMix[24];
      snprintf(expectedMix, sizeof(expectedMix), "reward_mix_b%u_c%u",
               bubble, creature);
      assert(strcmp(AudioPlan::rewardMixId(bubble, creature), expectedMix) == 0);
      assert(strcmp(AudioPlan::rewardPraiseId(bubble, creature),
                    praises[(bubble + creature) % 4]) == 0);
    }
  }
  assert(AudioPlan::rewardMixId(4, 0) == nullptr);
  assert(AudioPlan::rewardMixId(0, 8) == nullptr);
  assert(AudioPlan::rewardPraiseId(4, 0) == nullptr);
  return 0;
}
