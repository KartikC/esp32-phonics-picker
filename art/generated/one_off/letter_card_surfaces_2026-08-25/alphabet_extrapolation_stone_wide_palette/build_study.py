#!/usr/bin/env python3
"""Build a deterministic wider-palette review sheet from the accepted RD stone."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[5]
STUDY_DIR = Path(__file__).resolve().parent
SOURCE = ROOT / (
    "art/generated/one_off/letter_card_surfaces_2026-08-25/retrodiffusion/"
    "option2_carved_tide_stone__82521.png"
)
OUTPUT = STUDY_DIR / "alphabet_2a_stonewashed_atkinson_contact_sheet.png"
MANIFEST = STUDY_DIR / "render_manifest.json"

SOURCE_SHA256 = "80bb7f65419280532000c5399e159334f607a9087b67dbf31adc53e62da9b0df"
ATKINSON_SOURCE_SHA256 = "5a455d1cfa099b601ab70751bb9673e8fe1854dc4500c80e1a220d0d75e31745"
SOURCE_BBOX = (20, 7, 108, 120)
CARD_SIZE = (138, 158)
SHEET_SIZE = (1136, 1310)

ROLE_COLORS = {
    (95, 143, 160): "main_body",
    (53, 103, 122): "body_shadow",
    (11, 42, 60): "deep_crevice",
    (216, 238, 240): "pale_mineral",
    (18, 74, 96): "deep_slate",
    (145, 183, 190): "mid_mineral",
    (247, 255, 255): "white_chip",
    (39, 211, 208): "cyan_glint",
}

MOTIFS = ("clustered dots", "diagonal rakes", "cross sparks", "square chips")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rgb_to_565(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def rgb_from_565(value: int) -> tuple[int, int, int]:
    r = (value >> 11) & 0x1F
    g = (value >> 5) & 0x3F
    b = value & 0x1F
    return (
        round(r * 255 / 31),
        round(g * 255 / 63),
        round(b * 255 / 31),
    )


def mix(a: tuple[int, int, int], b: tuple[int, int, int], b_amount: float) -> tuple[int, int, int]:
    return tuple(round(x * (1.0 - b_amount) + y * b_amount) for x, y in zip(a, b))


def stonewashed_palette() -> list[int]:
    # A deliberately narrow, low-saturation mineral family. Hue and value
    # still separate the learning anchors, but every member reads as weathered
    # clay, lichen, sea glass, slate, or heather rather than painted plastic.
    rgb_values = (
        (140, 98, 83),   (88, 120, 106),  (118, 100, 127), (122, 120, 77),
        (82, 111, 124),  (128, 96, 107),  (94, 118, 91),   (105, 99, 129),
        (138, 112, 77),  (83, 122, 119),  (125, 93, 117),  (107, 119, 79),
        (93, 110, 130),  (140, 93, 82),   (82, 116, 95),   (101, 95, 131),
        (130, 116, 78),  (84, 116, 124),  (130, 93, 104),  (95, 120, 81),
        (112, 95, 133),  (137, 98, 72),   (90, 119, 111),  (117, 93, 120),
        (116, 120, 72),  (83, 108, 130),
    )
    values = [rgb_to_565(rgb) for rgb in rgb_values]
    assert len(values) == len(set(values)) == 26
    return values


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = ROOT / (
        "vendor/waveshare-esp32-s3-touch-amoled-1.8/examples/arduino-v2/"
        "libraries/lvgl/scripts/built_in_font"
    ) / name
    if not path.exists():
        path = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
                    "/System/Library/Fonts/Supplemental/Arial.ttf")
    return ImageFont.truetype(str(path), size)


def glyph_masks(selected_font: ImageFont.FreeTypeFont,
                letter_index: int) -> tuple[Image.Image, Image.Image]:
    letter = chr(ord("a") + letter_index)
    left, top, right, bottom = selected_font.getbbox(letter, anchor="ls")
    width, height = right - left, bottom - top
    native = Image.new("1", (width, height), 0)
    ImageDraw.Draw(native).text(
        (-left, -top), letter, font=selected_font, anchor="ls", fill=255
    )
    glyph = Image.new("L", CARD_SIZE, 0)
    glyph.paste(native.convert("L"), (
        (CARD_SIZE[0] - width) // 2,
        (CARD_SIZE[1] - height) // 2,
    ))
    outline = glyph.filter(ImageFilter.MaxFilter(5))
    outline = ImageChops.subtract(outline, glyph)
    return glyph, outline


def letter_anchors(letter: str) -> list[tuple[int, int]]:
    state = 0x9E3779B9 ^ ((ord(letter) - ord("a") + 1) * 0x45D9F3B)
    anchors = []
    for _ in range(13):
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        x = 17 + ((state >> 8) % (CARD_SIZE[0] - 34))
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        y = 18 + ((state >> 8) % (CARD_SIZE[1] - 36))
        anchors.append((x, y))
    return anchors


def motif_mask(letter_index: int, offset: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", CARD_SIZE, 0)
    draw = ImageDraw.Draw(mask)
    ox, oy = offset
    for index, (x, y) in enumerate(letter_anchors(chr(ord("a") + letter_index))):
        x += ox
        y += oy
        family = letter_index % 4
        if family == 0:
            radius = 2 + index % 2
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
            draw.ellipse((x + 4, y - 3, x + 5, y - 2), fill=255)
        elif family == 1:
            draw.line((x - 4, y + 3, x + 4, y - 3), fill=255, width=1)
            draw.line((x - 2, y + 4, x + 5, y - 1), fill=255, width=1)
        elif family == 2:
            draw.line((x - 3, y, x + 3, y), fill=255, width=1)
            draw.line((x, y - 3, x, y + 3), fill=255, width=1)
            draw.point((x + 4, y + 3), fill=255)
        else:
            draw.rectangle((x - 2, y - 2, x + 2, y + 2), outline=255, width=1)
            draw.point((x + 4, y - 3), fill=255)
    return mask


def render_card(role_image: Image.Image, selected_font: ImageFont.FreeTypeFont,
                letter_index: int, base565: int) -> Image.Image:
    base = rgb_from_565(base565)
    main = mix(base, (0, 0, 0), 0.22)
    colors = {
        "main_body": main,
        "body_shadow": mix(main, (0, 0, 0), 0.22),
        "deep_crevice": mix((11, 42, 60), main, 0.15),
        "pale_mineral": mix((216, 238, 240), main, 0.26),
        "deep_slate": mix((18, 74, 96), main, 0.23),
        "mid_mineral": mix((145, 183, 190), main, 0.30),
        "white_chip": (247, 255, 255),
        "cyan_glint": mix((39, 211, 208), main, 0.05),
    }
    card = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    main_mask = Image.new("L", CARD_SIZE, 0)
    for y in range(CARD_SIZE[1]):
        for x in range(CARD_SIZE[0]):
            rgba = role_image.getpixel((x, y))
            if rgba[3] == 0:
                continue
            role = ROLE_COLORS[rgba[:3]]
            card.putpixel((x, y), (*colors[role], 255))
            if role == "main_body":
                main_mask.putpixel((x, y), 255)

    light = mix(main, colors["pale_mineral"], 0.10)
    dark = mix(main, (0, 0, 0), 0.16)
    light_mask = ImageChops.multiply(motif_mask(letter_index, (-1, -1)), main_mask)
    dark_mask = ImageChops.multiply(motif_mask(letter_index, (0, 0)), main_mask)
    card.paste((*light, 255), (0, 0, *CARD_SIZE), light_mask)
    card.paste((*dark, 255), (0, 0, *CARD_SIZE), dark_mask)

    glyph, outline = glyph_masks(selected_font, letter_index)
    card.paste((11, 42, 60, 255), (0, 0, *CARD_SIZE), outline)
    card.paste((247, 255, 255, 255), (0, 0, *CARD_SIZE), glyph)
    return card


def main() -> None:
    if sha256(SOURCE) != SOURCE_SHA256:
        raise SystemExit("RD 82521 source hash changed")
    atkinson_source = Path(os.environ.get(
        "ATKINSON_FONT_SOURCE",
        "/tmp/phonics-font-study-2026-08-25/AtkinsonHyperlegibleNext.ttf",
    )).expanduser()
    if not atkinson_source.is_file() or sha256(atkinson_source) != ATKINSON_SOURCE_SHA256:
        raise SystemExit("selected Atkinson Hyperlegible Next source is missing or changed")
    source = Image.open(SOURCE).convert("RGBA")
    if source.getbbox() != SOURCE_BBOX:
        raise SystemExit("RD 82521 alpha bounds changed")
    opaque_colors = {
        pixel[:3] for pixel in source.get_flattened_data() if pixel[3]
    }
    if opaque_colors != set(ROLE_COLORS):
        raise SystemExit("RD 82521 semantic palette changed")

    role_image = source.crop(SOURCE_BBOX).resize(CARD_SIZE, Image.Resampling.NEAREST)
    selected_font = ImageFont.truetype(str(atkinson_source), 112)
    selected_font.set_variation_by_axes([800])
    palette = stonewashed_palette()

    background = (4, 17, 27)
    cell_color = (12, 48, 66)
    sheet = Image.new("RGB", SHEET_SIZE, background)
    draw = ImageDraw.Draw(sheet)
    draw.text((28, 18), "2A v5 - stonewashed + Atkinson", font=font(28, True), fill=(255, 228, 151))
    draw.text(
        (28, 57),
        "Exact RD 82521 stone; 26 permanent tints stay inside one weathered clay, lichen, sea-glass and slate family.",
        font=font(13), fill=(151, 188, 198),
    )
    draw.text(
        (28, 85),
        "Atkinson Hyperlegible Next ExtraBold 800 is one-bit rasterized and centered; cool mineral planes stay fixed.",
        font=font(13), fill=(219, 237, 240),
    )

    for index, base565 in enumerate(palette):
        row, column = divmod(index, 6)
        cell_x = 32 + column * 176
        cell_y = 126 + row * 232
        draw.rounded_rectangle((cell_x, cell_y, cell_x + 160, cell_y + 222),
                               radius=12, fill=cell_color)
        card = render_card(role_image, selected_font, index, base565)
        alpha = card.getchannel("A")
        shadow = Image.new("RGBA", CARD_SIZE, (4, 11, 17, 255))
        # Center the 138 px card body exactly in the 160 px review cell. The
        # shadow retains the shipping three-by-six offset behind that center.
        sheet.paste(shadow.convert("RGB"), (cell_x + 14, cell_y + 15), alpha)
        sheet.paste(card.convert("RGB"), (cell_x + 11, cell_y + 9), alpha)
        letter = chr(ord("a") + index)
        draw.text((cell_x + 9, cell_y + 184), f"{letter} | 0x{base565:04X}",
                  font=font(13, True), fill=(222, 238, 240))
        draw.text((cell_x + 9, cell_y + 205), MOTIFS[index % 4],
                  font=font(11), fill=(147, 183, 194))

    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    sheet.save(OUTPUT, optimize=True)
    manifest = {
        "schema_version": 1,
        "purpose": "Review-only combined 2A stonewashed cards with selected Atkinson letter face.",
        "production_asset": False,
        "openai_image_generation_used": False,
        "new_generation_calls": 0,
        "source_rd_png": str(SOURCE.relative_to(ROOT)),
        "source_rd_sha256": SOURCE_SHA256,
        "source_alpha_bbox": list(SOURCE_BBOX),
        "selected_font": "Atkinson Hyperlegible Next ExtraBold 800",
        "selected_font_source_sha256": ATKINSON_SOURCE_SHA256,
        "palette_strategy": "hand-tuned low-saturation clay, lichen, sage, sea-glass, slate, heather, and ochre family",
        "fixed_elements": [
            "RD 82521 alpha silhouette and all eight semantic regions",
            "cool mineral planes, chips, cracks, and cyan glints",
            "letter-derived seed, 13 anchors, and four motif families",
            "Atkinson Hyperlegible Next ExtraBold 800 one-bit glyph treatment",
            "each visible glyph centered from its own rendered bounds",
            "each 138-pixel card body centered in its 160-pixel review cell",
        ],
        "palette": [
            {"letter": chr(ord("a") + i), "base_rgb565": f"0x{value:04X}",
             "motif_family": MOTIFS[i % 4]}
            for i, value in enumerate(palette)
        ],
        "output": {
            "path": str(OUTPUT.relative_to(ROOT)),
            "sha256": sha256(OUTPUT),
            "size": list(sheet.size),
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(OUTPUT)
    print(manifest["output"]["sha256"])


if __name__ == "__main__":
    main()
