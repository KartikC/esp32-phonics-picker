#pragma once

#include <stdint.h>

#include "CardStoneAsset.h"

namespace phonics_game {

struct StoneRolePalette {
  uint16_t colors[kStoneRoleCount];

  constexpr uint16_t operator[](uint8_t role) const {
    return colors[role];
  }
};

constexpr uint16_t stoneBlend565(uint16_t foreground, uint16_t background,
                                 uint8_t amount) {
  const uint16_t fr = (foreground >> 11) & 0x1f;
  const uint16_t fg = (foreground >> 5) & 0x3f;
  const uint16_t fb = foreground & 0x1f;
  const uint16_t br = (background >> 11) & 0x1f;
  const uint16_t bg = (background >> 5) & 0x3f;
  const uint16_t bb = background & 0x1f;
  const uint16_t r = (fr * amount + br * (255 - amount)) / 255;
  const uint16_t g = (fg * amount + bg * (255 - amount)) / 255;
  const uint16_t b = (fb * amount + bb * (255 - amount)) / 255;
  return static_cast<uint16_t>((r << 11) | (g << 5) | b);
}

// Keep every mineral plane in the letter's stonewashed hue family. Earlier
// fixed cyan and navy source colors became green specks and blue linework on
// the CO5300 AMOLED. These narrow value steps retain the carved texture while
// preventing any role from becoming an unrelated saturated accent.
constexpr StoneRolePalette makeStoneRolePalette(uint16_t baseColor,
                                                bool pulsing) {
  StoneRolePalette palette{};
  const uint16_t mainBody = stoneBlend565(
      baseColor, 0x0000, pulsing ? 215 : 199);
  palette.colors[kStoneTransparent] = 0x0000;
  palette.colors[kStoneMainBody] = mainBody;
  palette.colors[kStoneBodyShadow] =
      stoneBlend565(mainBody, 0x0000, 217);
  palette.colors[kStoneDeepCrevice] =
      stoneBlend565(mainBody, 0x0000, 178);
  palette.colors[kStonePaleMineral] =
      stoneBlend565(mainBody, 0xffff, 225);
  palette.colors[kStoneDeepSlate] =
      stoneBlend565(mainBody, 0x0000, 204);
  palette.colors[kStoneMidMineral] =
      stoneBlend565(mainBody, 0xffff, 242);
  palette.colors[kStoneWhiteChip] =
      stoneBlend565(mainBody, 0xffff, 204);
  palette.colors[kStoneCyanGlint] =
      stoneBlend565(mainBody, 0xffff, 230);
  return palette;
}

}  // namespace phonics_game
