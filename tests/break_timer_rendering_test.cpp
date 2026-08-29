#include <cassert>
#include <cstring>
#include <iostream>

#include "../firmware/PhonicsGame/BreakTimerRendering.h"

using namespace phonics_game;

int main() {
  static_assert(kBreakTimerIconTop >= 0);
  static_assert(kBreakCountdownCenterX == kScreenWidth / 2);
  static_assert(kBreakProgressLeft >= 0);
  static_assert(kBreakProgressLeft + kBreakProgressWidth <= kScreenWidth);
  static_assert(kBreakProgressTop + kBreakProgressHeight < kBreakLabelCenterY);
  static_assert(kBreakLabelCenterY < kScreenHeight);

  char countdown[6]{};
  formatBreakCountdown(1800, countdown);
  assert(std::strcmp(countdown, "30:00") == 0);
  formatBreakCountdown(1799, countdown);
  assert(std::strcmp(countdown, "29:59") == 0);
  formatBreakCountdown(900, countdown);
  assert(std::strcmp(countdown, "15:00") == 0);
  formatBreakCountdown(1, countdown);
  assert(std::strcmp(countdown, "00:01") == 0);
  formatBreakCountdown(0, countdown);
  assert(std::strcmp(countdown, "00:00") == 0);
  formatBreakCountdown(100000, countdown);
  assert(std::strcmp(countdown, "99:59") == 0);

  assert(breakProgressPixels(kPlayBreakDurationMs) == 0);
  assert(breakProgressPixels(kPlayBreakDurationMs / 2) ==
         kBreakProgressWidth / 2);
  assert(breakProgressPixels(1) == kBreakProgressWidth - 1);
  assert(breakProgressPixels(0) == kBreakProgressWidth);
  assert(breakProgressPixels(kPlayBreakDurationMs + 1) == 0);

  std::cout << "break timer rendering contract passed\n";
  return 0;
}
