#pragma once

#include <stdint.h>

namespace phonics_game {

constexpr uint32_t kMaintenanceMuteDoubleTapWindowMs = 500;
constexpr uint32_t kMaintenanceMuteDisconnectDebounceMs = 1800;

enum class MaintenanceMuteEvent : uint8_t {
  none,
  replay,
  toggled,
};

// A small, platform-independent state machine for the USB-only maintenance
// mute gesture. The caller owns hit testing: innerReplayTap() is for the full
// replay target while USB data is present; outerReplayTap() provides immediate
// replay when the USB-only gesture is unavailable.
class MaintenanceMuteController {
 public:
  // rawDataConnected may momentarily flap false on an otherwise healthy USB
  // link. Keep the effective gesture/indicator connection alive until a false
  // sample has remained stable for the full disconnect debounce.
  MaintenanceMuteEvent update(uint32_t nowMs, bool rawDataConnected) {
    if (rawDataConnected) {
      disconnectObserved_ = false;
      dataConnected_ = true;
    } else if (dataConnected_) {
      beginDisconnectIfNeeded(nowMs);
      if (elapsed(nowMs, disconnectObservedAtMs_) >=
          kMaintenanceMuteDisconnectDebounceMs) {
        dataConnected_ = false;
        const bool autoUnmuted = muted_;
        muted_ = false;

        // Once the sustained disconnect is real, a tap that was waiting for
        // a possible double tap can no longer become a mute gesture. Release
        // it as replay. The caller also observes dataConnected() changing and
        // redraws the indicator even when replay is the primary event.
        if (pending_) {
          pending_ = false;
          return MaintenanceMuteEvent::replay;
        }
        if (autoUnmuted) return MaintenanceMuteEvent::toggled;
      }
    }

    if (pending_ && elapsed(nowMs, pendingAtMs_) >=
                        kMaintenanceMuteDoubleTapWindowMs) {
      pending_ = false;
      return MaintenanceMuteEvent::replay;
    }

    return MaintenanceMuteEvent::none;
  }

  MaintenanceMuteEvent innerReplayTap(uint32_t nowMs) {
    if (!dataConnected_) {
      pending_ = false;
      return MaintenanceMuteEvent::replay;
    }

    if (!pending_) {
      pending_ = true;
      pendingAtMs_ = nowMs;
      return MaintenanceMuteEvent::none;
    }

    if (elapsed(nowMs, pendingAtMs_) <
        kMaintenanceMuteDoubleTapWindowMs) {
      pending_ = false;
      muted_ = !muted_;
      return MaintenanceMuteEvent::toggled;
    }

    // The old tap has matured into replay. Keep this new tap pending so it can
    // still be paired with a following tap without losing either action.
    pendingAtMs_ = nowMs;
    return MaintenanceMuteEvent::replay;
  }

  MaintenanceMuteEvent outerReplayTap() {
    pending_ = false;
    return MaintenanceMuteEvent::replay;
  }

  // Serial diagnostics use the same data-cable gate as the gesture. Unmute is
  // always allowed so a maintenance command can never strand audio off.
  MaintenanceMuteEvent setMuted(bool enabled) {
    pending_ = false;
    if (enabled && !dataConnected_) return MaintenanceMuteEvent::none;
    if (muted_ == enabled) return MaintenanceMuteEvent::none;
    muted_ = enabled;
    return MaintenanceMuteEvent::toggled;
  }

  void cancelPending() { pending_ = false; }

  bool pending() const { return pending_; }
  bool muted() const { return muted_; }
  bool dataConnected() const { return dataConnected_; }

 private:
  static uint32_t elapsed(uint32_t nowMs, uint32_t thenMs) {
    return nowMs - thenMs;
  }

  void beginDisconnectIfNeeded(uint32_t nowMs) {
    if (disconnectObserved_) return;
    disconnectObserved_ = true;
    disconnectObservedAtMs_ = nowMs;
  }

  bool pending_ = false;
  bool muted_ = false;
  bool dataConnected_ = false;
  bool disconnectObserved_ = false;
  uint32_t pendingAtMs_ = 0;
  uint32_t disconnectObservedAtMs_ = 0;
};

}  // namespace phonics_game
