#pragma once

#include <stdint.h>

namespace phonics_game {

constexpr uint8_t kAudioVolumePercent = 80;

class AudioEngine {
 public:
  static bool begin();
  static bool ready();
  static void play(const char* assetId);
  static void playSequence(const char* firstId, const char* secondId);
};

}  // namespace phonics_game
