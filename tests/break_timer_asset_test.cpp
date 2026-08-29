#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>

#include "../firmware/PhonicsGame/BreakTimerAsset.h"

using namespace phonics_game;

int main() {
  static_assert(kBreakTimerWidth == 128);
  static_assert(kBreakTimerHeight == 128);
  static_assert(kBreakTimerPackedBytes == 8192);
  static_assert(kBreakTimerOpaquePixels == 8078);
  static_assert(kBreakTimerAlphaLeft == 23);
  static_assert(kBreakTimerAlphaTop == 1);
  static_assert(kBreakTimerAlphaRight == 105);
  static_assert(kBreakTimerAlphaBottom == 128);
  static_assert(kBreakTimerPalette[kBreakTimerTransparent] == 0x0000);
  static_assert(kBreakTimerPalette[kBreakTimerSand] == 0xF5AD);
  static_assert(kBreakTimerPalette[kBreakTimerSandHighlight] == 0xF713);

  constexpr uint16_t expectedPalette[10] = {
      0x0000, 0x00A4, 0x0947, 0x124C, 0x332F,
      0x5C74, 0x95B7, 0xDF7E, 0xF5AD, 0xF713,
  };
  constexpr uint16_t expectedCounts[10] = {
      8306, 1885, 283, 1338, 2280, 506, 152, 316, 1313, 5,
  };
  std::array<uint32_t, 10> actualCounts{};
  for (uint16_t y = 0; y < kBreakTimerHeight; ++y) {
    for (uint16_t x = 0; x < kBreakTimerWidth; ++x) {
      const uint8_t role = breakTimerRoleAt(x, y);
      assert(role < 10);
      ++actualCounts[role];
    }
  }
  uint32_t total = 0;
  for (uint8_t role = 0; role < 10; ++role) {
    assert(kBreakTimerPalette[role] == expectedPalette[role]);
    assert(kBreakTimerRolePixelCounts[role] == expectedCounts[role]);
    assert(actualCounts[role] == expectedCounts[role]);
    total += actualCounts[role];
  }
  assert(total == kBreakTimerWidth * kBreakTimerHeight);
  assert(total - actualCounts[kBreakTimerTransparent] ==
         kBreakTimerOpaquePixels);

  assert(breakTimerRoleAt(0, 0) == kBreakTimerTransparent);
  assert(breakTimerRoleAt(127, 0) == kBreakTimerTransparent);
  assert(breakTimerRoleAt(0, 127) == kBreakTimerTransparent);
  assert(breakTimerRoleAt(127, 127) == kBreakTimerTransparent);

  std::cout << "break timer asset contract passed\n";
  return 0;
}
