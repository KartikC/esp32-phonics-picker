#include <assert.h>
#include <stdint.h>

#include "../firmware/PhonicsGame/CreatureRewardSelector.h"

using namespace phonics_game;

namespace {

bool samePlan(const CreatureRewardPlan& left,
              const CreatureRewardPlan& right) {
  return left.creatureIndex == right.creatureIndex &&
         left.paletteIndex == right.paletteIndex &&
         left.patternStyle == right.patternStyle &&
         left.patternSeed == right.patternSeed && left.rare == right.rare;
}

void assertValid(const CreatureRewardPlan& plan) {
  assert(plan.creatureIndex < CreatureRewardSelector::kCreatureCount);
  assert(CreatureRewardSelector::isAutomaticPalette(plan.paletteIndex));
  assert(CreatureRewardSelector::isAutomaticPaletteForCreature(
      plan.creatureIndex, plan.paletteIndex));
  assert(plan.paletteIndex != 3);
  assert(plan.patternStyle < CreatureRewardSelector::kPatternCount);
  if (plan.rare) {
    assert(plan.patternStyle ==
           static_cast<uint8_t>(RewardPatternStyle::kSolid));
  }
}

uint32_t seedWithCommonPrefix(uint8_t commonCount, bool wrongAfterCorrect) {
  for (uint32_t seed = 0; seed < 100000; ++seed) {
    CreatureRewardSelector selector(seed);
    bool allCommon = true;
    for (uint8_t index = 0; index < commonCount; ++index) {
      if (selector.onCorrect().rare) {
        allCommon = false;
        break;
      }
      if (wrongAfterCorrect) selector.onWrong();
    }
    if (allCommon) return seed;
  }
  assert(false && "could not find deterministic common-prefix test seed");
  return 0;
}

}  // namespace

int main() {
  assert(CreatureRewardSelector::kCreatureCount == 8);
  const uint8_t expectedWeights[8] = {80, 13, 30, 80, 80, 13, 30, 13};
  for (uint8_t creature = 0; creature < 8; ++creature) {
    assert(CreatureRewardSelector::speciesBaseWeight(creature) ==
           expectedWeights[creature]);
  }
  assert(CreatureRewardSelector::speciesBaseTier(0) == CreatureBaseTier::kBasic);
  assert(CreatureRewardSelector::speciesBaseTier(3) == CreatureBaseTier::kBasic);
  assert(CreatureRewardSelector::speciesBaseTier(4) == CreatureBaseTier::kBasic);
  assert(CreatureRewardSelector::speciesBaseTier(2) == CreatureBaseTier::kMedium);
  assert(CreatureRewardSelector::speciesBaseTier(6) == CreatureBaseTier::kMedium);
  assert(CreatureRewardSelector::speciesBaseTier(1) == CreatureBaseTier::kRare);
  assert(CreatureRewardSelector::speciesBaseTier(5) == CreatureBaseTier::kRare);
  assert(CreatureRewardSelector::speciesBaseTier(7) == CreatureBaseTier::kRare);

  // Glass squid and sea angel keep their translucent pale ramps. All other
  // species use the full automatic set, and plum is never automatic.
  for (uint8_t creature = 0; creature < 8; ++creature) {
    for (uint8_t palette = 0; palette < 6; ++palette) {
      const bool paleRestricted = creature == 4 || creature == 6;
      const bool expected = paleRestricted
                                ? (palette == 0 || palette == 1 || palette == 5)
                                : (palette == 0 || palette == 1 || palette == 2 ||
                                   palette == 4 || palette == 5);
      assert(CreatureRewardSelector::isAutomaticPaletteForCreature(
                 creature, palette) == expected);
    }
  }

  assert(CreatureRewardSelector::rareOddsDenominator(0) == 50);
  assert(CreatureRewardSelector::rareOddsDenominator(3) == 50);
  assert(CreatureRewardSelector::rareOddsDenominator(4) == 25);
  assert(CreatureRewardSelector::rareOddsDenominator(7) == 25);
  assert(CreatureRewardSelector::rareOddsDenominator(8) == 13);
  assert(CreatureRewardSelector::rareOddsDenominator(9) == 13);

  // Identical seed and answer history must produce an identical, stable reward
  // stream.
  CreatureRewardSelector deterministicA(0x12345678u);
  CreatureRewardSelector deterministicB(0x12345678u);
  for (uint16_t answer = 0; answer < 256; ++answer) {
    if (answer == 4 || answer == 19 || answer == 71) {
      deterministicA.onWrong();
      deterministicB.onWrong();
    }
    assert(samePlan(deterministicA.onCorrect(),
                    deterministicB.onCorrect()));
  }

  // A wrong answer changes only clean rarity progress: it does not advance the
  // reward stream or perturb the next visual draw.
  const uint32_t wrongIsolationSeed = seedWithCommonPrefix(2, false);
  CreatureRewardSelector withWrong(wrongIsolationSeed);
  CreatureRewardSelector withoutWrong(wrongIsolationSeed);
  assert(samePlan(withWrong.onCorrect(), withoutWrong.onCorrect()));
  withWrong.onWrong();
  assert(withWrong.cleanProgress() == 0);
  assert(withoutWrong.cleanProgress() == 1);
  assert(withWrong.correctCount() == withoutWrong.correctCount());
  assert(samePlan(withWrong.onCorrect(), withoutWrong.onCorrect()));
  assert(withWrong.correctCount() == withoutWrong.correctCount());

  // Exercise the actual onCorrect path across many independent seeds. Random
  // pre-guarantee rares must exist in every tier, common draws must remain,
  // and the observed incidence must rise with the documented odds.
  uint32_t tierRare[3] = {};
  uint32_t tierTotal[3] = {};
  constexpr uint32_t kTierSeedCount = 65536;
  constexpr uint8_t kTierPrefix[3] = {0, 4, 8};
  for (uint32_t seed = 0; seed < kTierSeedCount; ++seed) {
    for (uint8_t tier = 0; tier < 3; ++tier) {
      CreatureRewardSelector selector(seed);
      bool reachedTier = true;
      for (uint8_t answer = 0; answer < kTierPrefix[tier]; ++answer) {
        if (selector.onCorrect().rare) {
          reachedTier = false;
          break;
        }
      }
      if (!reachedTier) continue;
      ++tierTotal[tier];
      if (selector.onCorrect().rare) ++tierRare[tier];
    }
  }
  for (uint8_t tier = 0; tier < 3; ++tier) {
    assert(tierRare[tier] > 0);
    assert(tierRare[tier] < tierTotal[tier]);
  }
  assert(static_cast<uint64_t>(tierRare[0]) * tierTotal[1] <
         static_cast<uint64_t>(tierRare[1]) * tierTotal[0]);
  assert(static_cast<uint64_t>(tierRare[1]) * tierTotal[2] <
         static_cast<uint64_t>(tierRare[2]) * tierTotal[1]);

  // Exercise bounds, the non-purple palette allowlist, rare-solid behavior,
  // and immediate-repeat avoidance across many independent streams.
  bool observedSpeciesPalette[8][6] = {};
  for (uint32_t seed = 0; seed < 256; ++seed) {
    CreatureRewardSelector selector(seed);
    CreatureRewardPlan previous{};
    bool hasPrevious = false;
    for (uint16_t answer = 0; answer < 512; ++answer) {
      const CreatureRewardPlan plan = selector.onCorrect();
      assertValid(plan);
      observedSpeciesPalette[plan.creatureIndex][plan.paletteIndex] = true;
      if (hasPrevious) {
        assert(plan.creatureIndex != previous.creatureIndex);
        assert(plan.paletteIndex != previous.paletteIndex);
      }
      previous = plan;
      hasPrevious = true;
      if ((answer % 7) == 6) selector.onWrong();
    }
  }
  for (uint8_t creature = 0; creature < 8; ++creature) {
    for (uint8_t palette = 0; palette < 6; ++palette) {
      const bool allowed =
          CreatureRewardSelector::isAutomaticPaletteForCreature(creature,
                                                                 palette);
      assert(observedSpeciesPalette[creature][palette] == allowed);
    }
  }

  // Base-species tiering has its own deterministic domain and remains
  // independent of visual-treatment rarity. Wrong answers deliberately make
  // the rare-treatment histories diverge without perturbing species draws.
  CreatureRewardSelector speciesWithErrors(0xA55AA55Au);
  CreatureRewardSelector speciesClean(0xA55AA55Au);
  bool sawTreatmentDifference = false;
  for (uint16_t answer = 0; answer < 512; ++answer) {
    if ((answer % 3) == 0) speciesWithErrors.onWrong();
    const CreatureRewardPlan errorPlan = speciesWithErrors.onCorrect();
    const CreatureRewardPlan cleanPlan = speciesClean.onCorrect();
    assert(errorPlan.creatureIndex == cleanPlan.creatureIndex);
    if (errorPlan.rare != cleanPlan.rare) sawTreatmentDifference = true;
  }
  assert(sawTreatmentDifference);

  // For transition P(i->j)=weight(j)/(total-weight(i)), detailed balance gives
  // stationary mass weight(i)*(total-weight(i)). Thus the exact tier shares
  // are 62,160/93,414, 18,540/93,414, and 12,714/93,414. Check the stream stays
  // close to those values as well as enforcing zero immediate repeats above.
  uint32_t speciesTierCounts[3] = {};
  constexpr uint32_t kSpeciesSamples = 1000000;
  CreatureRewardSelector speciesDistribution(0x51EC1E5u);
  for (uint32_t answer = 0; answer < kSpeciesSamples; ++answer) {
    const CreatureRewardPlan plan = speciesDistribution.onCorrect();
    ++speciesTierCounts[static_cast<uint8_t>(
        CreatureRewardSelector::speciesBaseTier(plan.creatureIndex))];
  }
  constexpr uint32_t kExpectedNumerators[3] = {62160, 18540, 12714};
  for (uint8_t tier = 0; tier < 3; ++tier) {
    const uint64_t observedScaled =
        static_cast<uint64_t>(speciesTierCounts[tier]) * 93414;
    const uint64_t expectedScaled =
        static_cast<uint64_t>(kSpeciesSamples) * kExpectedNumerators[tier];
    const uint64_t difference = observedScaled > expectedScaled
                                    ? observedScaled - expectedScaled
                                    : expectedScaled - observedScaled;
    assert(difference <
           static_cast<uint64_t>(kSpeciesSamples) * 93414 / 250);  // 0.4%.
  }

  // A clean run guarantees its rare on the tenth correct if random rarity
  // has not already reset the run.
  const uint32_t cleanSeed = seedWithCommonPrefix(9, false);
  CreatureRewardSelector cleanGuarantee(cleanSeed);
  for (uint8_t answer = 1; answer <= 9; ++answer) {
    assert(!cleanGuarantee.onCorrect().rare);
    assert(cleanGuarantee.cleanProgress() == answer);
  }
  assert(cleanGuarantee.onCorrect().rare);
  assert(cleanGuarantee.cleanProgress() == 0);
  assert(cleanGuarantee.correctsSinceRare() == 0);

  // Errors reset the clean run but preserve lifetime progress toward the pity
  // rare. With every answer made non-clean, the fourteenth correct is forced.
  const uint32_t pitySeed = seedWithCommonPrefix(13, true);
  CreatureRewardSelector pityGuarantee(pitySeed);
  for (uint8_t answer = 1; answer <= 13; ++answer) {
    assert(!pityGuarantee.onCorrect().rare);
    assert(pityGuarantee.cleanProgress() == 1);
    assert(pityGuarantee.correctsSinceRare() == answer);
    pityGuarantee.onWrong();
    assert(pityGuarantee.cleanProgress() == 0);
    assert(pityGuarantee.correctsSinceRare() == answer);
  }
  const CreatureRewardPlan pityPlan = pityGuarantee.onCorrect();
  assert(pityPlan.rare);
  assert(pityGuarantee.cleanProgress() == 0);
  assert(pityGuarantee.correctsSinceRare() == 0);

  // The selected policy should feel rare but attainable during uninterrupted
  // play, while its guarantees prevent an unbounded dry spell.
  uint32_t rareCount = 0;
  uint32_t longestGap = 0;
  uint32_t currentGap = 0;
  CreatureRewardSelector distribution(0xC0FFEEu);
  constexpr uint32_t kSampleCount = 100000;
  for (uint32_t answer = 0; answer < kSampleCount; ++answer) {
    if (distribution.onCorrect().rare) {
      ++rareCount;
      if (currentGap > longestGap) longestGap = currentGap;
      currentGap = 0;
    } else {
      ++currentGap;
    }
  }
  if (currentGap > longestGap) longestGap = currentGap;
  assert(rareCount > kSampleCount / 20);  // More than 5%.
  assert(rareCount < kSampleCount / 6);   // Less than 16.7%.
  assert(longestGap <= CreatureRewardSelector::kCleanStreakGuarantee - 1);

  return 0;
}
