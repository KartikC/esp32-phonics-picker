#include <assert.h>
#include <stdint.h>

#include "../firmware/PhonicsGame/AudioIdlePolicy.h"

using namespace phonics_game;

int main() {
  constexpr uint32_t finishedAt = 1000;
  assert(!AudioIdlePolicy::shouldPowerDown(
      finishedAt + kAudioIdlePowerDownMs - 1, finishedAt, true, false, false));
  assert(AudioIdlePolicy::shouldPowerDown(
      finishedAt + kAudioIdlePowerDownMs, finishedAt, true, false, false));

  // A queued command or the cross-core audio task always keeps the output up.
  assert(!AudioIdlePolicy::shouldPowerDown(
      finishedAt + kAudioIdlePowerDownMs, finishedAt, true, true, false));
  assert(!AudioIdlePolicy::shouldPowerDown(
      finishedAt + kAudioIdlePowerDownMs, finishedAt, true, false, true));
  assert(!AudioIdlePolicy::shouldPowerDown(
      finishedAt + kAudioIdlePowerDownMs, finishedAt, false, false, false));

  // The unsigned elapsed-time check remains correct across millis() wrap.
  constexpr uint32_t wrappingFinishedAt = UINT32_MAX - 100;
  assert(!AudioIdlePolicy::shouldPowerDown(
      static_cast<uint32_t>(wrappingFinishedAt + kAudioIdlePowerDownMs - 1),
      wrappingFinishedAt, true, false, false));
  assert(AudioIdlePolicy::shouldPowerDown(
      static_cast<uint32_t>(wrappingFinishedAt + kAudioIdlePowerDownMs),
      wrappingFinishedAt, true, false, false));

  return 0;
}
