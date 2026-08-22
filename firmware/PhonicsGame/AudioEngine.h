#pragma once

#include <stdint.h>

namespace phonics_game {

constexpr uint8_t kAudioVolumePercent = 100;

class AudioEngine {
 public:
  static bool begin();
  static bool ready();
  static bool suspend();
  static bool resume();
  static void play(const char* assetId);
  static void playSequence(const char* firstId, const char* secondId);
};

}  // namespace phonics_game
