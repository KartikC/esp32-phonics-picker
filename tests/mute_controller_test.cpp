#include <assert.h>
#include <stdint.h>

#include "../firmware/PhonicsGame/MaintenanceMuteController.h"

using namespace phonics_game;

int main() {
  // A USB-data-connected inner tap waits for the double-tap window before it
  // becomes a normal replay.
  MaintenanceMuteController singleTap;
  assert(singleTap.update(900, true) == MaintenanceMuteEvent::none);
  assert(singleTap.dataConnected());
  assert(singleTap.innerReplayTap(1000) ==
         MaintenanceMuteEvent::none);
  assert(singleTap.pending());
  assert(singleTap.update(
             1000 + kMaintenanceMuteDoubleTapWindowMs - 1, true) ==
         MaintenanceMuteEvent::none);
  assert(singleTap.update(1000 + kMaintenanceMuteDoubleTapWindowMs, true) ==
         MaintenanceMuteEvent::replay);
  assert(!singleTap.pending());
  assert(!singleTap.muted());

  // A second inner tap in the window toggles mute and consumes both taps.
  MaintenanceMuteController doubleTap;
  assert(doubleTap.update(1900, true) == MaintenanceMuteEvent::none);
  assert(doubleTap.innerReplayTap(2000) ==
         MaintenanceMuteEvent::none);
  assert(doubleTap.innerReplayTap(2100) ==
         MaintenanceMuteEvent::toggled);
  assert(doubleTap.muted());
  assert(!doubleTap.pending());
  assert(doubleTap.update(2500, true) == MaintenanceMuteEvent::none);

  // A natural 400 ms double tap remains inside the device gesture window.
  MaintenanceMuteController naturalDoubleTap;
  assert(naturalDoubleTap.update(2600, true) == MaintenanceMuteEvent::none);
  assert(naturalDoubleTap.innerReplayTap(2700) == MaintenanceMuteEvent::none);
  assert(naturalDoubleTap.innerReplayTap(3100) ==
         MaintenanceMuteEvent::toggled);
  assert(naturalDoubleTap.muted());

  // The same gesture toggles mute back off.
  assert(doubleTap.innerReplayTap(3200) ==
         MaintenanceMuteEvent::none);
  assert(doubleTap.innerReplayTap(3300) ==
         MaintenanceMuteEvent::toggled);
  assert(!doubleTap.muted());

  // The outer-only part of the replay hit target is never delayed and also
  // cancels an inner tap that was waiting for a partner.
  assert(doubleTap.innerReplayTap(4000) ==
         MaintenanceMuteEvent::none);
  assert(doubleTap.outerReplayTap() == MaintenanceMuteEvent::replay);
  assert(!doubleTap.pending());
  assert(doubleTap.update(5000, true) == MaintenanceMuteEvent::none);

  // Without an actual USB data host, every replay hit is immediate and mute
  // cannot be entered, even with rapid repeated taps.
  MaintenanceMuteController noData;
  assert(noData.innerReplayTap(6000) ==
         MaintenanceMuteEvent::replay);
  assert(noData.innerReplayTap(6050) ==
         MaintenanceMuteEvent::replay);
  assert(!noData.pending());
  assert(!noData.muted());

  // A transient raw disconnect neither hides the effective data connection
  // nor breaks a valid double-tap gesture. Reconnection resets its debounce.
  MaintenanceMuteController transientDisconnect;
  assert(transientDisconnect.update(6900, true) ==
         MaintenanceMuteEvent::none);
  assert(transientDisconnect.innerReplayTap(7000) ==
         MaintenanceMuteEvent::none);
  assert(transientDisconnect.update(7010, false) ==
         MaintenanceMuteEvent::none);
  assert(transientDisconnect.dataConnected());
  assert(transientDisconnect.pending());
  assert(transientDisconnect.innerReplayTap(7100) ==
         MaintenanceMuteEvent::toggled);
  assert(transientDisconnect.muted());
  assert(transientDisconnect.update(7200, true) ==
         MaintenanceMuteEvent::none);
  assert(transientDisconnect.dataConnected());
  assert(transientDisconnect.muted());

  // A brief host disconnect does not unmute. Reconnection resets the debounce,
  // while a full sustained disconnect does unmute and emits a state change.
  MaintenanceMuteController disconnect;
  assert(disconnect.update(7900, true) == MaintenanceMuteEvent::none);
  assert(disconnect.innerReplayTap(8000) ==
         MaintenanceMuteEvent::none);
  assert(disconnect.innerReplayTap(8100) ==
         MaintenanceMuteEvent::toggled);
  assert(disconnect.muted());
  assert(disconnect.update(9000, false) == MaintenanceMuteEvent::none);
  assert(disconnect.update(
             9000 + kMaintenanceMuteDisconnectDebounceMs - 1, false) ==
         MaintenanceMuteEvent::none);
  assert(disconnect.dataConnected());
  assert(disconnect.muted());
  assert(disconnect.update(10800, true) == MaintenanceMuteEvent::none);
  assert(disconnect.muted());
  assert(disconnect.update(11000, false) == MaintenanceMuteEvent::none);
  assert(disconnect.update(
             11000 + kMaintenanceMuteDisconnectDebounceMs, false) ==
         MaintenanceMuteEvent::toggled);
  assert(!disconnect.muted());
  assert(!disconnect.dataConnected());

  // A tap during the disconnect grace period must not reset the original raw
  // disconnect timer. When that timer matures, pending replay is released,
  // mute is cleared, and the effective connection drops together.
  MaintenanceMuteController replayAndUnmute;
  assert(replayAndUnmute.update(11400, true) ==
         MaintenanceMuteEvent::none);
  assert(replayAndUnmute.innerReplayTap(11500) ==
         MaintenanceMuteEvent::none);
  assert(replayAndUnmute.innerReplayTap(11600) ==
         MaintenanceMuteEvent::toggled);
  assert(replayAndUnmute.update(12000, false) ==
         MaintenanceMuteEvent::none);
  assert(replayAndUnmute.innerReplayTap(13000) ==
         MaintenanceMuteEvent::none);
  assert(replayAndUnmute.update(
             12000 + kMaintenanceMuteDisconnectDebounceMs, false) ==
         MaintenanceMuteEvent::replay);
  assert(!replayAndUnmute.muted());
  assert(!replayAndUnmute.dataConnected());

  // Explicit cancellation drops a delayed replay without changing mute.
  MaintenanceMuteController cancelled;
  assert(cancelled.update(12900, true) == MaintenanceMuteEvent::none);
  assert(cancelled.innerReplayTap(13000) ==
         MaintenanceMuteEvent::none);
  cancelled.cancelPending();
  assert(!cancelled.pending());
  assert(cancelled.update(14000, true) == MaintenanceMuteEvent::none);
  assert(!cancelled.muted());

  MaintenanceMuteController serialControl;
  assert(serialControl.setMuted(true) == MaintenanceMuteEvent::none);
  assert(!serialControl.muted());
  assert(serialControl.update(14500, true) == MaintenanceMuteEvent::none);
  assert(serialControl.setMuted(true) == MaintenanceMuteEvent::toggled);
  assert(serialControl.muted());
  assert(serialControl.setMuted(true) == MaintenanceMuteEvent::none);
  assert(serialControl.setMuted(false) == MaintenanceMuteEvent::toggled);
  assert(!serialControl.muted());

  // All elapsed-time checks remain valid across the uint32_t millis() wrap.
  MaintenanceMuteController wrappingTap;
  const uint32_t tapStart = UINT32_MAX - 100;
  assert(wrappingTap.update(tapStart - 1, true) ==
         MaintenanceMuteEvent::none);
  assert(wrappingTap.innerReplayTap(tapStart) ==
         MaintenanceMuteEvent::none);
  assert(wrappingTap.update(
             static_cast<uint32_t>(tapStart +
                                   kMaintenanceMuteDoubleTapWindowMs - 1),
             true) == MaintenanceMuteEvent::none);
  assert(wrappingTap.update(
             static_cast<uint32_t>(tapStart +
                                   kMaintenanceMuteDoubleTapWindowMs),
             true) == MaintenanceMuteEvent::replay);

  MaintenanceMuteController wrappingDisconnect;
  const uint32_t muteStart = UINT32_MAX - 500;
  assert(wrappingDisconnect.update(muteStart - 1, true) ==
         MaintenanceMuteEvent::none);
  assert(wrappingDisconnect.innerReplayTap(muteStart) ==
         MaintenanceMuteEvent::none);
  assert(wrappingDisconnect.innerReplayTap(
             static_cast<uint32_t>(muteStart + 100)) ==
         MaintenanceMuteEvent::toggled);
  const uint32_t disconnectStart = UINT32_MAX - 50;
  assert(wrappingDisconnect.update(disconnectStart, false) ==
         MaintenanceMuteEvent::none);
  assert(wrappingDisconnect.update(
             static_cast<uint32_t>(disconnectStart +
                                   kMaintenanceMuteDisconnectDebounceMs),
             false) == MaintenanceMuteEvent::toggled);
  assert(!wrappingDisconnect.muted());

  return 0;
}
