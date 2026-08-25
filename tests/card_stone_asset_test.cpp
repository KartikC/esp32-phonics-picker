#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>

#include "../firmware/PhonicsGame/CardStoneAsset.h"
#include "../firmware/PhonicsGame/CardStoneRendering.h"

using namespace phonics_game;

int main() {
  static_assert(kStoneSourceWidth == 88);
  static_assert(kStoneSourceHeight == 113);
  static_assert(kStoneSourcePixelCount == 9944);
  static_assert(kStonePackedBytes == 4972);
  static_assert(kStoneShadowColor == 0x0042);
  static_assert(kStoneShadowColor != 0x0204);
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

  // Every visible stone role is derived from the letter's muted base color.
  // The old fixed cyan glint and navy mineral lines were conspicuous on the
  // AMOLED and must never return as shared high-chroma artifacts.
  for (bool pulsing : {false, true}) {
    for (uint8_t letter = 0; letter < 26; ++letter) {
      const StoneRolePalette palette =
          makeStoneRolePalette(kStoneLetterColors[letter], pulsing);
      assert(palette[kStoneTransparent] == 0x0000);
      assert(palette[kStoneWhiteChip] != 0xffff);
      for (uint8_t role = kStoneMainBody; role < kStoneRoleCount; ++role) {
        assert(palette[role] != 0x2659);  // Former near-neon cyan glint.
        const uint16_t red = ((palette[role] >> 11) & 0x1f) * 255 / 31;
        const uint16_t green = ((palette[role] >> 5) & 0x3f) * 255 / 63;
        const uint16_t blue = (palette[role] & 0x1f) * 255 / 31;
        assert(red < 180 && green < 180 && blue < 180);
      }
      const auto channel = [](uint16_t color, uint8_t shift,
                              uint16_t mask) {
        return static_cast<uint16_t>((color >> shift) & mask);
      };
      for (const auto component :
           {std::array<uint16_t, 2>{11, 0x1f},
            std::array<uint16_t, 2>{5, 0x3f},
            std::array<uint16_t, 2>{0, 0x1f}}) {
        const uint8_t shift = static_cast<uint8_t>(component[0]);
        const uint16_t mask = component[1];
        assert(channel(palette[kStoneDeepCrevice], shift, mask) <=
               channel(palette[kStoneDeepSlate], shift, mask));
        assert(channel(palette[kStoneDeepSlate], shift, mask) <=
               channel(palette[kStoneBodyShadow], shift, mask));
        assert(channel(palette[kStoneBodyShadow], shift, mask) <=
               channel(palette[kStoneMainBody], shift, mask));
        assert(channel(palette[kStoneMainBody], shift, mask) <=
               channel(palette[kStoneMidMineral], shift, mask));
        assert(channel(palette[kStoneMidMineral], shift, mask) <=
               channel(palette[kStoneCyanGlint], shift, mask));
        assert(channel(palette[kStoneCyanGlint], shift, mask) <=
               channel(palette[kStonePaleMineral], shift, mask));
        assert(channel(palette[kStonePaleMineral], shift, mask) <=
               channel(palette[kStoneWhiteChip], shift, mask));
      }
    }
  }
  for (uint8_t role = kStoneMainBody; role < kStoneRoleCount; ++role) {
    uint8_t distinctColors = 0;
    for (uint8_t letter = 0; letter < 26; ++letter) {
      const uint16_t candidate =
          makeStoneRolePalette(kStoneLetterColors[letter], false)[role];
      bool firstOccurrence = true;
      for (uint8_t earlier = 0; earlier < letter; ++earlier) {
        if (makeStoneRolePalette(kStoneLetterColors[earlier], false)[role] ==
            candidate) {
          firstOccurrence = false;
          break;
        }
      }
      if (firstOccurrence) ++distinctColors;
    }
    assert(distinctColors >= 16);
  }

  std::cout << "card stone asset contract passed\n";
  return 0;
}
