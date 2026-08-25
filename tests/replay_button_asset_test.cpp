#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>

#include "../firmware/PhonicsGame/LayoutGeometry.h"
#include "../firmware/PhonicsGame/ReplayButtonAsset.h"

using namespace phonics_game;

int main() {
  static_assert(kReplayButtonWidth == 64);
  static_assert(kReplayButtonHeight == 64);
  static_assert(kReplayButtonPackedBytes == 2048);
  static_assert(kReplayButtonOpaquePixels == 3024);
  static_assert(kReplayButtonAlphaLeft == 1);
  static_assert(kReplayButtonAlphaTop == 1);
  static_assert(kReplayButtonAlphaRight == 63);
  static_assert(kReplayButtonAlphaBottom == 63);
  static_assert(kReplayButtonPlayLeft == 24);
  static_assert(kReplayButtonPlayTop == 19);
  static_assert(kReplayButtonPlayRight == 46);
  static_assert(kReplayButtonPlayBottom == 45);
  static_assert(kReplayVisualRadius == 32);
  static_assert(kReplayVisualRadius < kReplayHitRadius);
  static_assert(kReplayCenterX - kReplayVisualRadius >= 0);
  static_assert(kReplayCenterY - kReplayVisualRadius >= 0);
  static_assert(kReplayCenterX + kReplayVisualRadius <= kScreenWidth);
  static_assert(kReplayCenterY + kReplayVisualRadius <= kScreenHeight);
  static_assert(kReplayButtonPalette[kReplayButtonTransparent] == 0x0000);
  static_assert(kReplayButtonPalette[kReplayButtonFace] == 0x124C);
  static_assert(kReplayButtonPalette[kReplayButtonPlayGlyph] == 0xF7FF);

  constexpr uint16_t expectedPalette[9] = {
      0x0000, 0x00A4, 0x0947, 0x124C, 0x332F,
      0x5C74, 0x95B7, 0xDF7E, 0xF7FF,
  };
  constexpr uint16_t expectedCounts[9] = {
      1072, 539, 2, 922, 590, 4, 1, 637, 329,
  };
  std::array<uint32_t, 9> actualCounts{};
  for (uint16_t y = 0; y < kReplayButtonHeight; ++y) {
    for (uint16_t x = 0; x < kReplayButtonWidth; ++x) {
      const uint8_t role = replayButtonRoleAt(x, y);
      assert(role < 9);
      ++actualCounts[role];
    }
  }
  uint32_t total = 0;
  for (uint8_t role = 0; role < 9; ++role) {
    assert(kReplayButtonPalette[role] == expectedPalette[role]);
    assert(kReplayButtonRolePixelCounts[role] == expectedCounts[role]);
    assert(actualCounts[role] == expectedCounts[role]);
    total += actualCounts[role];
  }
  assert(total == kReplayButtonWidth * kReplayButtonHeight);
  assert(total - actualCounts[kReplayButtonTransparent] ==
         kReplayButtonOpaquePixels);

  // All four canvas corners stay transparent and the white role remains solely
  // the selected button's play glyph beneath the optional mute slash.
  assert(replayButtonRoleAt(0, 0) == kReplayButtonTransparent);
  assert(replayButtonRoleAt(63, 0) == kReplayButtonTransparent);
  assert(replayButtonRoleAt(0, 63) == kReplayButtonTransparent);
  assert(replayButtonRoleAt(63, 63) == kReplayButtonTransparent);
  assert(actualCounts[kReplayButtonPlayGlyph] == 329);

  std::cout << "replay button asset contract passed\n";
  return 0;
}
