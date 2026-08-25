#!/usr/bin/env python3
"""Build the selected Atkinson Hyperlegible Next card font for Arduino GFX."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "firmware/PhonicsGame/fonts/AtkinsonHyperlegibleNextExtraBold112.h"
REPORT = ROOT / "art/fonts/generated/atkinson_hyperlegible_next_report.json"
CONTACT_SHEET = ROOT / (
    "art/generated/one_off/font_comparison_2026-08-25/"
    "atkinson_full_alphabet_contact_sheet.png"
)

SOURCE_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/"
    "atkinsonhyperlegiblenext/AtkinsonHyperlegibleNext%5Bwght%5D.ttf"
)
LICENSE_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/"
    "atkinsonhyperlegiblenext/OFL.txt"
)
SOURCE_SHA256 = "5a455d1cfa099b601ab70751bb9673e8fe1854dc4500c80e1a220d0d75e31745"
CONTACT_SHEET_SHA256 = "f7581b20245bc02a4b27528c525dcdfee38697adee9fdff41d852b1e727ef795"
FONT_SIZE = 112
FONT_AXIS_WEIGHT = 800
FIRST = ord("a")
LAST = ord("z")
CARD_SIZE = (138, 158)
HALO_RADIUS = 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packed_glyph(font: ImageFont.FreeTypeFont, character: str):
    left, top, right, bottom = font.getbbox(character, anchor="ls")
    width, height = max(0, right - left), max(0, bottom - top)
    advance = round(font.getlength(character))
    if not width or not height:
        return b"", width, height, advance, left, top
    image = Image.new("1", (width, height), 0)
    ImageDraw.Draw(image).text(
        (-left, -top), character, font=font, fill=255, anchor="ls"
    )
    output = bytearray()
    byte = bits = 0
    for pixel in image.get_flattened_data():
        byte, bits = (byte << 1) | int(bool(pixel)), bits + 1
        if bits == 8:
            output.append(byte)
            byte = bits = 0
    if bits:
        output.append(byte << (8 - bits))
    return bytes(output), width, height, advance, left, top


def format_header(bitmap: bytearray, glyphs: list[tuple[int, ...]]) -> str:
    name = "AtkinsonHyperlegibleNextExtraBold112"
    lines = [
        "#pragma once",
        '#include "gfxfont.h"',
        "",
        "// Atkinson Hyperlegible Next ExtraBold 800, 112 px, lowercase a-z.",
        f"// Source SHA-256: {SOURCE_SHA256}",
        f"const uint8_t {name}Bitmaps[] PROGMEM = {{",
    ]
    for start in range(0, len(bitmap), 12):
        lines.append(
            "  " + ", ".join(
                f"0x{value:02X}" for value in bitmap[start:start + 12]
            ) + ","
        )
    lines += ["};", "", f"const GFXglyph {name}Glyphs[] PROGMEM = {{"]
    for codepoint, glyph in zip(range(FIRST, LAST + 1), glyphs):
        offset, width, height, advance, x_offset, y_offset = glyph
        lines.append(
            "  { %5d, %3d, %3d, %3d, %3d, %3d }, // 0x%02X" %
            (offset, width, height, advance, x_offset, y_offset, codepoint)
        )
    lines += [
        "};", "", f"const GFXfont {name} PROGMEM = {{",
        f"  (uint8_t*){name}Bitmaps, (GFXglyph*){name}Glyphs,",
        f"  0x{FIRST:02X}, 0x{LAST:02X}, {FONT_SIZE}", "};", "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path,
        default=Path(os.environ.get(
            "ATKINSON_FONT_SOURCE",
            "/tmp/phonics-font-study-2026-08-25/AtkinsonHyperlegibleNext.ttf",
        )),
    )
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"missing selected Atkinson source: {source}")
    if sha256(source) != SOURCE_SHA256:
        raise SystemExit("selected Atkinson source hash changed")
    if sha256(CONTACT_SHEET) != CONTACT_SHEET_SHA256:
        raise SystemExit("selected Atkinson contact-sheet hash changed")

    font = ImageFont.truetype(str(source), FONT_SIZE)
    font.set_variation_by_axes([FONT_AXIS_WEIGHT])
    bitmap = bytearray()
    glyphs: list[tuple[int, ...]] = []
    metrics = []
    for codepoint in range(FIRST, LAST + 1):
        character = chr(codepoint)
        data, width, height, advance, x_offset, y_offset = packed_glyph(
            font, character
        )
        if not data or not any(data):
            raise SystemExit(f"generated blank glyph for {character!r}")
        glyphs.append((len(bitmap), width, height, advance, x_offset, y_offset))
        bitmap.extend(data)
        fits = (
            width + HALO_RADIUS * 2 <= CARD_SIZE[0] and
            height + HALO_RADIUS * 2 <= CARD_SIZE[1]
        )
        if not fits:
            raise SystemExit(f"{character!r} does not fit the production card")
        metrics.append({
            "letter": character,
            "width": width,
            "height": height,
            "advance": advance,
            "x_offset": x_offset,
            "y_offset": y_offset,
            "halo_fit": fits,
        })

    OUTPUT.write_text(format_header(bitmap, glyphs))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "status": "passed",
        "selected_font": "Atkinson Hyperlegible Next",
        "selected_weight": "ExtraBold 800",
        "nominal_pixel_size": FONT_SIZE,
        "glyph_range": "a-z",
        "license": "SIL Open Font License 1.1",
        "license_url": LICENSE_URL,
        "source_url": SOURCE_URL,
        "source_sha256": SOURCE_SHA256,
        "builder": str(Path(__file__).resolve().relative_to(ROOT)),
        "builder_sha256": sha256(Path(__file__).resolve()),
        "selection_contact_sheet": str(CONTACT_SHEET.relative_to(ROOT)),
        "selection_contact_sheet_sha256": CONTACT_SHEET_SHA256,
        "header": str(OUTPUT.relative_to(ROOT)),
        "header_sha256": sha256(OUTPUT),
        "bitmap_bytes": len(bitmap),
        "card_size": list(CARD_SIZE),
        "halo_radius": HALO_RADIUS,
        "max_glyph_width": max(item["width"] for item in metrics),
        "max_glyph_height": max(item["height"] for item in metrics),
        "all_glyphs_fit": all(item["halo_fit"] for item in metrics),
        "glyphs": metrics,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(bitmap)} bitmap bytes)")
    print(f"Wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
