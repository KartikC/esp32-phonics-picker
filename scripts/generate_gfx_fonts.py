#!/usr/bin/env python3
"""Convert Letterboard's Nunito faces into compact Arduino GFX fonts."""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
LETTERBOARD = Path(os.environ.get("LETTERBOARD_ROOT", ROOT.parent / "Letterboard"))
SOURCE = LETTERBOARD / "android/app/src/main/res/font"


def packed_glyph(font, character):
    left, top, right, bottom = font.getbbox(character, anchor="ls")
    width, height = max(0, right - left), max(0, bottom - top)
    advance = round(font.getlength(character))
    if not width or not height:
        return b"", width, height, advance, left, top
    image = Image.new("1", (width, height), 0)
    ImageDraw.Draw(image).text((-left, -top), character, font=font, fill=255,
                               anchor="ls")
    output, byte, bits = bytearray(), 0, 0
    for pixel in image.getdata():
        byte, bits = (byte << 1) | int(bool(pixel)), bits + 1
        if bits == 8:
            output.append(byte)
            byte, bits = 0, 0
    if bits:
        output.append(byte << (8 - bits))
    return bytes(output), width, height, advance, left, top


def emit(source, size, first, last, name, output):
    font, bitmap, glyphs = ImageFont.truetype(str(source), size), bytearray(), []
    for codepoint in range(first, last + 1):
        data, width, height, advance, x_offset, y_offset = packed_glyph(font, chr(codepoint))
        if not chr(codepoint).isspace() and (not data or not any(data)):
            raise RuntimeError(f"generated blank glyph for {chr(codepoint)!r}")
        glyphs.append((len(bitmap), width, height, advance, x_offset, y_offset))
        bitmap.extend(data)
    lines = ["#pragma once", '#include "gfxfont.h"', "", f"const uint8_t {name}Bitmaps[] PROGMEM = {{"]
    for start in range(0, len(bitmap), 12):
        lines.append("  " + ", ".join(f"0x{x:02X}" for x in bitmap[start:start + 12]) + ",")
    lines += ["};", "", f"const GFXglyph {name}Glyphs[] PROGMEM = {{"]
    for codepoint, glyph in zip(range(first, last + 1), glyphs):
        offset, width, height, advance, x_offset, y_offset = glyph
        lines.append("  { %5d, %3d, %3d, %3d, %3d, %3d }, // 0x%02X" %
                     (offset, width, height, advance, x_offset, y_offset, codepoint))
    lines += ["};", "", f"const GFXfont {name} PROGMEM = {{",
              f"  (uint8_t*){name}Bitmaps, (GFXglyph*){name}Glyphs,",
              f"  0x{first:02X}, 0x{last:02X}, {size}", "};", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))
    print(f"{output.relative_to(ROOT)}: {len(bitmap)} bitmap bytes")


def main():
    output = ROOT / "firmware/PhonicsGame/fonts"
    emit(SOURCE / "nunito_black.ttf", 112, ord("a"), ord("z"),
         "NunitoBlack112", output / "NunitoBlack112.h")
    emit(SOURCE / "nunito_bold.ttf", 28, 32, 126,
         "NunitoBold28", output / "NunitoBold28.h")


if __name__ == "__main__":
    main()
