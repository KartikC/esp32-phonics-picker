#pragma once

#include <stdint.h>

namespace phonics_game {

// These ordinals intentionally match creature_variations::PatternStyle without
// importing the generated Arduino asset header into this pure C++ policy.
enum class RewardPatternStyle : uint8_t {
  kSolid = 0,
  kSpots = 1,
  kStripes = 2,
  kMottle = 3,
};

// These ordinals intentionally match variation_manifest.json. Species rarity
// controls how often a base creature appears; it is independent of the rare
// visual treatment stored in CreatureRewardPlan::rare.
enum class RewardCreature : uint8_t {
  kMoonJelly = 0,
  kReefShark = 1,
  kGiantOctopus = 2,
  kSeahorse = 3,
  kGlassSquid = 4,
  kAnglerfish = 5,
  kSeaAngel = 6,
  kGulperEel = 7,
};

enum class CreatureBaseTier : uint8_t {
  kBasic,
  kMedium,
  kRare,
};

struct CreatureRewardPlan {
  uint8_t creatureIndex;
  uint8_t paletteIndex;
  uint8_t patternStyle;
  uint32_t patternSeed;
  bool rare;
};

// Selects the visual reward shown after a correct answer. This owns an RNG
// domain that is deliberately separate from GameEngine, so adding reward
// variety can never change the phonics curriculum sequence.
class CreatureRewardSelector {
 public:
  static constexpr uint8_t kCreatureCount = 8;
  static constexpr uint8_t kPatternCount = 4;
  static constexpr uint8_t kAutomaticPaletteCount = 5;
  static constexpr uint8_t kCleanStreakGuarantee = 8;
  static constexpr uint8_t kCorrectPityGuarantee = 12;

  explicit CreatureRewardSelector(uint32_t seed) { reset(seed); }

  void reset(uint32_t seed) {
    seed_ = seed;
    correctCount_ = 0;
    cleanProgress_ = 0;
    correctsSinceRare_ = 0;
    previousCreatureSlot_ = 0;
    previousPaletteIndex_ = 0;
    hasPreviousReward_ = false;
  }

  CreatureRewardPlan onCorrect() {
    const uint8_t progressBeforeAnswer = cleanProgress_;
    ++correctCount_;
    ++cleanProgress_;
    ++correctsSinceRare_;

    bool rare = cleanProgress_ >= kCleanStreakGuarantee ||
                correctsSinceRare_ >= kCorrectPityGuarantee;
    if (!rare) {
      rare = bounded(randomFor(kRarityDomain),
                     rareOddsDenominator(progressBeforeAnswer)) == 0;
    }

    const uint8_t creatureSlot = chooseWeightedCreature(
        randomFor(kCreatureDomain), previousCreatureSlot_);
    const uint8_t paletteIndex = choosePaletteForCreature(
        randomFor(kPaletteDomain), creatureSlot, previousPaletteIndex_);

    CreatureRewardPlan plan{};
    plan.creatureIndex = creatureSlot;
    plan.paletteIndex = paletteIndex;
    plan.patternStyle = rare
                            ? static_cast<uint8_t>(RewardPatternStyle::kSolid)
                            : static_cast<uint8_t>(bounded(
                                  randomFor(kPatternDomain), kPatternCount));
    plan.patternSeed = randomFor(kPatternSeedDomain);
    plan.rare = rare;

    previousCreatureSlot_ = creatureSlot;
    previousPaletteIndex_ = paletteIndex;
    hasPreviousReward_ = true;
    if (rare) {
      cleanProgress_ = 0;
      correctsSinceRare_ = 0;
    }
    return plan;
  }

  // A wrong answer only breaks the clean run. The slower pity counter remains
  // intact so a learner who is making progress is never locked out of a rare.
  void onWrong() { cleanProgress_ = 0; }

  uint8_t cleanProgress() const { return cleanProgress_; }
  uint8_t correctsSinceRare() const { return correctsSinceRare_; }
  uint32_t correctCount() const { return correctCount_; }

  static constexpr bool isAutomaticPalette(uint8_t paletteIndex) {
    for (uint8_t index : kAutomaticPaletteIndices) {
      if (index == paletteIndex) return true;
    }
    return false;
  }

  static constexpr bool isAutomaticPaletteForCreature(
      uint8_t creatureIndex, uint8_t paletteIndex) {
    if (!isAutomaticPalette(paletteIndex)) return false;
    const bool usesPaleRestrictedRamp =
        creatureIndex == static_cast<uint8_t>(RewardCreature::kGlassSquid) ||
        creatureIndex == static_cast<uint8_t>(RewardCreature::kSeaAngel);
    return !usesPaleRestrictedRamp || paletteIndex == 0 ||
           paletteIndex == 1 || paletteIndex == 5;
  }

  // Device-rounded hazards plus the eighth-correct clean guarantee raise the
  // clean renewal incidence from 11.284% to 14.021% (+24.26%). The twelfth-
  // correct pity guarantee keeps an every-answer-wrong run at 9.453%, 16.45%
  // above the former 1/50 plus fourteenth-correct policy.
  static constexpr uint8_t rareOddsDenominator(
      uint8_t cleanProgressBeforeAnswer) {
    return cleanProgressBeforeAnswer <= 2
               ? 43
               : (cleanProgressBeforeAnswer <= 5 ? 21 : 11);
  }

  static constexpr CreatureBaseTier speciesBaseTier(uint8_t creatureIndex) {
    return creatureIndex == static_cast<uint8_t>(RewardCreature::kMoonJelly) ||
                   creatureIndex == static_cast<uint8_t>(RewardCreature::kSeahorse) ||
                   creatureIndex == static_cast<uint8_t>(RewardCreature::kGlassSquid)
               ? CreatureBaseTier::kBasic
               : (creatureIndex == static_cast<uint8_t>(RewardCreature::kGiantOctopus) ||
                          creatureIndex == static_cast<uint8_t>(RewardCreature::kSeaAngel)
                      ? CreatureBaseTier::kMedium
                      : CreatureBaseTier::kRare);
  }

  static constexpr uint8_t speciesBaseWeight(uint8_t creatureIndex) {
    return creatureIndex < kCreatureCount
               ? kCreatureBaseWeights[creatureIndex]
               : 0;
  }

 private:
  // Palette 3 is "Plum deep". It remains available to explicit authoring and
  // diagnostics, but is left out of automatic rewards.
  inline static constexpr uint8_t
      kAutomaticPaletteIndices[kAutomaticPaletteCount] = {0, 1, 2, 4, 5};

  // Per-species weights are 80:30:16 for basic:medium:rare. Compared with the
  // preceding 80:30:13 policy, this makes rare-tier species 17.87% more
  // frequent after immediate repeats are removed: 15,936/99,336, or 16.04%.
  // A weight of 15 would produce only a 12.08% effective increase because the
  // immediately previous species is removed before each later draw.
  // Manifest order: jelly, shark, octopus, seahorse, glass squid, anglerfish,
  // sea angel, gulper eel.
  inline static constexpr uint8_t kCreatureBaseWeights[kCreatureCount] = {
      80, 16, 30, 80, 80, 16, 30, 16};

  inline static constexpr uint32_t kRarityDomain = 0xA511E9B3u;
  inline static constexpr uint32_t kCreatureDomain = 0x43D2C8F1u;
  inline static constexpr uint32_t kPaletteDomain = 0x7186B4A5u;
  inline static constexpr uint32_t kPatternDomain = 0xC2B2AE35u;
  inline static constexpr uint32_t kPatternSeedDomain = 0x9E3779B9u;

  static constexpr uint32_t mix32(uint32_t value) {
    value ^= value >> 16;
    value *= 0x7FEB352Du;
    value ^= value >> 15;
    value *= 0x846CA68Bu;
    value ^= value >> 16;
    return value;
  }

  uint32_t randomFor(uint32_t domain) const {
    return mix32(seed_ ^ domain ^ mix32(correctCount_ + 0x9E3779B9u));
  }

  static uint16_t bounded(uint32_t value, uint16_t bound) {
    return static_cast<uint16_t>(
        (static_cast<uint64_t>(value) * bound) >> 32);
  }

  uint8_t chooseWeightedCreature(uint32_t value,
                                 uint8_t previousSlot) const {
    uint16_t eligibleWeight = 0;
    for (uint8_t slot = 0; slot < kCreatureCount; ++slot) {
      if (hasPreviousReward_ && slot == previousSlot) continue;
      eligibleWeight = static_cast<uint16_t>(
          eligibleWeight + kCreatureBaseWeights[slot]);
    }

    uint16_t draw = bounded(value, eligibleWeight);
    for (uint8_t slot = 0; slot < kCreatureCount; ++slot) {
      if (hasPreviousReward_ && slot == previousSlot) continue;
      const uint8_t weight = kCreatureBaseWeights[slot];
      if (draw < weight) return slot;
      draw = static_cast<uint16_t>(draw - weight);
    }
    return 0;  // Unreachable for a non-empty, positive-weight table.
  }

  uint8_t choosePaletteForCreature(uint32_t value, uint8_t creatureIndex,
                                   uint8_t previousPaletteIndex) const {
    uint8_t eligibleCount = 0;
    for (uint8_t paletteIndex : kAutomaticPaletteIndices) {
      if (!isAutomaticPaletteForCreature(creatureIndex, paletteIndex)) continue;
      if (hasPreviousReward_ && paletteIndex == previousPaletteIndex) continue;
      ++eligibleCount;
    }

    // All production species have at least three eligible palettes, so the
    // no-repeat set is non-empty. Keeping the fallback makes this helper safe
    // if a future species is intentionally constrained to a single palette.
    const bool canAvoidRepeat = eligibleCount > 0;
    if (!canAvoidRepeat) {
      for (uint8_t paletteIndex : kAutomaticPaletteIndices) {
        if (isAutomaticPaletteForCreature(creatureIndex, paletteIndex)) {
          ++eligibleCount;
        }
      }
    }

    uint8_t draw = bounded(value, eligibleCount);
    for (uint8_t paletteIndex : kAutomaticPaletteIndices) {
      if (!isAutomaticPaletteForCreature(creatureIndex, paletteIndex)) continue;
      if (canAvoidRepeat && hasPreviousReward_ &&
          paletteIndex == previousPaletteIndex) {
        continue;
      }
      if (draw == 0) return paletteIndex;
      --draw;
    }
    return kAutomaticPaletteIndices[0];  // Unreachable for production tables.
  }

  uint32_t seed_ = 0;
  uint32_t correctCount_ = 0;
  uint8_t cleanProgress_ = 0;
  uint8_t correctsSinceRare_ = 0;
  uint8_t previousCreatureSlot_ = 0;
  uint8_t previousPaletteIndex_ = 0;
  bool hasPreviousReward_ = false;
};

static_assert(static_cast<uint8_t>(RewardPatternStyle::kSolid) == 0,
              "pattern ordinals must match generated creature assets");
static_assert(static_cast<uint8_t>(RewardPatternStyle::kMottle) == 3,
              "pattern ordinals must match generated creature assets");
static_assert(static_cast<uint8_t>(RewardCreature::kGulperEel) + 1 ==
                  CreatureRewardSelector::kCreatureCount,
              "creature ordinals must match generated creature assets");

}  // namespace phonics_game
