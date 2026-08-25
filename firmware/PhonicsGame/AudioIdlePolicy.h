#pragma once

#include <stdint.h>

namespace phonics_game {

// Leave a generous silent tail after the final authored 40 ms gap before
// touching the analog path. The next command wakes the codec synchronously
// before its first PCM frame is queued.
constexpr uint32_t kAudioIdlePowerDownMs = 750;

class AudioIdlePolicy {
 public:
  static bool shouldPowerDown(uint32_t nowMs, uint32_t playbackFinishedAtMs,
                              bool playbackHasFinished, bool taskBusy,
                              bool commandQueued) {
    return playbackHasFinished && !taskBusy && !commandQueued &&
           elapsed(nowMs, playbackFinishedAtMs) >= kAudioIdlePowerDownMs;
  }

 private:
  static uint32_t elapsed(uint32_t nowMs, uint32_t thenMs) {
    return nowMs - thenMs;
  }
};

}  // namespace phonics_game
