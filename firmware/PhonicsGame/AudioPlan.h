#pragma once

#include <stdint.h>
#include <stdio.h>

#include "AudioEngine.h"

namespace phonics_game {

// Playback is enabled at the managed logical-100 level configured by AudioEngine.
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
    "wrong_not_it_try_again",
    "wrong_try_the_other_one",
};

constexpr const char* kPraisePromptIds[] = {
    "praise_nice_job",
    "praise_great_work",
    "praise_you_got_it",
    "praise_thats_it",
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

  static void praise(uint8_t variant) {
    if constexpr (!kAudioPlaybackEnabled) return;
    AudioEngine::play(kPraisePromptIds[variant]);
  }

 private:
  static void logSequence(const char* promptId, char target) {
    char phonicsId[10];
    snprintf(phonicsId, sizeof(phonicsId), "cowboy_%c", target);
    AudioEngine::playSequence(promptId, phonicsId);
  }
};

}  // namespace phonics_game
