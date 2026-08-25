#pragma once

#include <stdint.h>

namespace phonics_game {

constexpr uint8_t kAudioVolumePercent = 90;

class AudioEngine {
 public:
  static bool begin();
  static bool ready();
  static bool suspend();
  static bool resume();
  static void service(uint32_t nowMs);
  static const char* powerState();
  static uint32_t idlePowerDownCount();
  static uint32_t writeFailureCount();
  static void play(const char* assetId);
  static void playSequence(const char* firstId, const char* secondId);
  static void playCelebration(const char* rewardMixId);
};

}  // namespace phonics_game
