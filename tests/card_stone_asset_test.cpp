#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>

#include "../firmware/PhonicsGame/CardStoneAsset.h"

using namespace phonics_game;

int main() {
  static_assert(kStoneSourceWidth == 88);
  static_assert(kStoneSourceHeight == 113);
  static_assert(kStoneSourcePixelCount == 9944);
  static_assert(kStonePackedBytes == 4972);
  static_assert(sizeof(kStoneLetterColors) / sizeof(kStoneLetterColors[0]) == 26);
  static_assert(sizeof(kStoneRolePixelCounts) /
                    sizeof(kStoneRolePixelCounts[0]) == kStoneRoleCount);

  std::array<uint32_t, kStoneRoleCount> actualCounts{};
  for (uint16_t y = 0; y < kStoneSourceHeight; ++y) {
    for (uint16_t x = 0; x < kStoneSourceWidth; ++x) {
      const uint8_t role = stoneRoleAt(x, y);
      assert(role < kStoneRoleCount);
      ++actualCounts[role];
    }
  }
  uint32_t total = 0;
  for (uint8_t role = 0; role < kStoneRoleCount; ++role) {
    assert(actualCounts[role] == kStoneRolePixelCounts[role]);
    assert(actualCounts[role] > 0);
    total += actualCounts[role];
  }
  assert(total == kStoneSourcePixelCount);
  assert(actualCounts[kStoneMainBody] > actualCounts[kStoneBodyShadow]);
  assert(actualCounts[kStoneWhiteChip] < actualCounts[kStonePaleMineral]);
  assert(actualCounts[kStoneCyanGlint] < actualCounts[kStonePaleMineral]);

  for (uint8_t left = 0; left < 26; ++left) {
    assert(kStoneLetterColors[left] != 0);
    for (uint8_t right = left + 1; right < 26; ++right) {
      assert(kStoneLetterColors[left] != kStoneLetterColors[right]);
    }
  }

  std::cout << "card stone asset contract passed\n";
  return 0;
}
