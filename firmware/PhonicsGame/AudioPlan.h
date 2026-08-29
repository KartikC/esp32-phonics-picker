#pragma once

#include <stdint.h>
#include <stdio.h>

#include "AudioEngine.h"

namespace phonics_game {

// Playback is enabled at the managed level configured by AudioEngine.
constexpr bool kAudioPlaybackEnabled = true;

constexpr const char* kInitialPromptIds[] = {
    "prompt_which_one_says",
    "prompt_can_you_find",
    "prompt_which_letter_makes",
    "prompt_tap_the_one_that_says",
    "prompt_listen_which_one_says",
};

constexpr const char* kNudgePromptIds[] = {
    "nudge_have_another_listen",
    "nudge_take_your_time",
    "nudge_listen_once_more",
    "nudge_which_one_do_you_think",
};

constexpr const char* kWrongPromptIds[] = {
    "wrong_no_no",
};

constexpr const char* kPraisePromptIds[] = {
    "praise_nice_job",
    "praise_great_work",
    "praise_you_got_it",
    "praise_thats_it",
};

constexpr const char* kBubbleSfxIds[] = {
    "sfx_bubble_round",
    "sfx_bubble_even",
    "sfx_bubble_hollow",
    "sfx_bubble_cascade",
};

// These ordinals match RewardCreature and the generated creature asset roster.
constexpr const char* kCreatureSfxIds[] = {
    "sfx_creature_moon_jelly",
    "sfx_creature_reef_shark",
    "sfx_creature_giant_octopus",
    "sfx_creature_seahorse",
    "sfx_creature_glass_squid",
    "sfx_creature_anglerfish",
    "sfx_creature_sea_angel",
    "sfx_creature_gulper_eel",
};

// Each accepted celebration is authored offline as one PCM asset. The bubble
// selector remains the random, no-immediate-repeat domain and also chooses the
// paired praise line, so all four voices survive without a runtime mixer.
constexpr const char* kRewardMixIds[4][8] = {
    {
        "reward_mix_b0_c0", "reward_mix_b0_c1", "reward_mix_b0_c2",
        "reward_mix_b0_c3", "reward_mix_b0_c4", "reward_mix_b0_c5",
        "reward_mix_b0_c6", "reward_mix_b0_c7",
    },
    {
        "reward_mix_b1_c0", "reward_mix_b1_c1", "reward_mix_b1_c2",
        "reward_mix_b1_c3", "reward_mix_b1_c4", "reward_mix_b1_c5",
        "reward_mix_b1_c6", "reward_mix_b1_c7",
    },
    {
        "reward_mix_b2_c0", "reward_mix_b2_c1", "reward_mix_b2_c2",
        "reward_mix_b2_c3", "reward_mix_b2_c4", "reward_mix_b2_c5",
        "reward_mix_b2_c6", "reward_mix_b2_c7",
    },
    {
        "reward_mix_b3_c0", "reward_mix_b3_c1", "reward_mix_b3_c2",
        "reward_mix_b3_c3", "reward_mix_b3_c4", "reward_mix_b3_c5",
        "reward_mix_b3_c6", "reward_mix_b3_c7",
    },
};

class AudioPlan {
 public:
  static constexpr bool enabled() { return kAudioPlaybackEnabled; }

  static bool ready() {
    if constexpr (kAudioPlaybackEnabled) return AudioEngine::ready();
    return false;
  }

  static bool begin() {
    if constexpr (kAudioPlaybackEnabled) return AudioEngine::begin();
    return false;
  }

  static bool suspend() {
    if constexpr (kAudioPlaybackEnabled) return AudioEngine::suspend();
    return true;
  }

  static bool resume() {
    if constexpr (kAudioPlaybackEnabled) return AudioEngine::resume();
    return true;
  }

  static void service(uint32_t nowMs) {
    if constexpr (kAudioPlaybackEnabled) AudioEngine::service(nowMs);
  }

  static const char* powerState() {
    if constexpr (kAudioPlaybackEnabled) return AudioEngine::powerState();
    return "disabled";
  }

  static uint32_t idlePowerDownCount() {
    if constexpr (kAudioPlaybackEnabled) {
      return AudioEngine::idlePowerDownCount();
    }
    return 0;
  }

  static uint32_t writeFailureCount() {
    if constexpr (kAudioPlaybackEnabled) {
      return AudioEngine::writeFailureCount();
    }
    return 0;
  }

  static void initial(uint8_t variant, char target) {
    if constexpr (!kAudioPlaybackEnabled) return;
    logSequence(kInitialPromptIds[variant], target);
  }

  static void nudge(uint8_t variant, char target) {
    if constexpr (!kAudioPlaybackEnabled) return;
    // "Which one do you think?" naturally follows the replayed sound; the
    // other nudge lines introduce it. This ordering is part of the authored
    // playback sequence.
    if (variant == 3) {
      char phonicsId[10];
      snprintf(phonicsId, sizeof(phonicsId), "cowboy_%c", target);
      AudioEngine::playSequence(phonicsId, kNudgePromptIds[variant]);
    } else {
      logSequence(kNudgePromptIds[variant], target);
    }
  }

  static void wrong(uint8_t variant) {
    if constexpr (!kAudioPlaybackEnabled) return;
    AudioEngine::play(kWrongPromptIds[variant]);
  }

  static constexpr uint8_t bubbleSfxCount() {
    return sizeof(kBubbleSfxIds) / sizeof(kBubbleSfxIds[0]);
  }

  static constexpr uint8_t creatureSfxCount() {
    return sizeof(kCreatureSfxIds) / sizeof(kCreatureSfxIds[0]);
  }

  static const char* bubbleSfxId(uint8_t variant) {
    return variant < bubbleSfxCount() ? kBubbleSfxIds[variant] : nullptr;
  }

  static const char* creatureSfxId(uint8_t creatureIndex) {
    return creatureIndex < creatureSfxCount()
               ? kCreatureSfxIds[creatureIndex]
               : nullptr;
  }

  static const char* rewardPraiseId(uint8_t bubbleVariant,
                                    uint8_t creatureIndex) {
    return bubbleVariant < bubbleSfxCount() &&
                   creatureIndex < creatureSfxCount()
               ? kPraisePromptIds[
                     (bubbleVariant + creatureIndex) % bubbleSfxCount()]
               : nullptr;
  }

  static const char* rewardMixId(uint8_t bubbleVariant,
                                 uint8_t creatureIndex) {
    return bubbleVariant < bubbleSfxCount() &&
                   creatureIndex < creatureSfxCount()
               ? kRewardMixIds[bubbleVariant][creatureIndex]
               : nullptr;
  }

  static void celebrate(uint8_t bubbleVariant, uint8_t creatureIndex) {
    if constexpr (!kAudioPlaybackEnabled) return;
    const char* mixId = rewardMixId(bubbleVariant, creatureIndex);
    if (mixId) AudioEngine::playCelebration(mixId);
  }

 private:
  static void logSequence(const char* promptId, char target) {
    char phonicsId[10];
    snprintf(phonicsId, sizeof(phonicsId), "cowboy_%c", target);
    AudioEngine::playSequence(promptId, phonicsId);
  }
};

}  // namespace phonics_game
