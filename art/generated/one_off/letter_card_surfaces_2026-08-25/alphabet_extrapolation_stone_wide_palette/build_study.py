#!/usr/bin/env python3
"""Build a deterministic wider-palette review sheet from the accepted RD stone."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[5]
STUDY_DIR = Path(__file__).resolve().parent
SOURCE = ROOT / (
    "art/generated/one_off/letter_card_surfaces_2026-08-25/retrodiffusion/"
    "option2_carved_tide_stone__82521.png"
)
OUTPUT = STUDY_DIR / "alphabet_2a_stonewashed_atkinson_contact_sheet.png"
MANIFEST = STUDY_DIR / "render_manifest.json"
PREVIEW_RENDERER = ROOT / "scripts/preview_on_device.py"

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


def load_preview_renderer():
    spec = importlib.util.spec_from_file_location("phonics_idle_renderer", PREVIEW_RENDERER)
    if spec is None or spec.loader is None:
        raise SystemExit("could not load the production idle renderer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_card(renderer, role_image: Image.Image,
                letter_index: int, base565: int) -> Image.Image:
    if renderer.COLORS_565[letter_index] != base565:
        raise SystemExit("review palette differs from the firmware palette")
    rendered = Image.new(
        "RGBA", (CARD_SIZE[0] + 3, CARD_SIZE[1] + 6), (0, 0, 0, 0)
    )
    renderer.card(
        rendered, chr(ord("a") + letter_index),
        (0, 0, CARD_SIZE[0], CARD_SIZE[1]), role_image,
    )
    return rendered


def main() -> None:
    if sha256(SOURCE) != SOURCE_SHA256:
        raise SystemExit("RD 82521 source hash changed")
    renderer = load_preview_renderer()
    if (sha256(renderer.FONT_HEADER) != renderer.FONT_HEADER_SHA256 or
            renderer.STONE_SOURCE_SHA256 != SOURCE_SHA256):
        raise SystemExit("production card renderer inputs are missing or changed")
    source = Image.open(SOURCE).convert("RGBA")
    if source.getbbox() != SOURCE_BBOX:
        raise SystemExit("RD 82521 alpha bounds changed")
    opaque_colors = {
        pixel[:3] for pixel in source.get_flattened_data() if pixel[3]
    }
    if opaque_colors != set(ROLE_COLORS):
        raise SystemExit("RD 82521 semantic palette changed")

    role_image = source.crop(SOURCE_BBOX)
    palette = stonewashed_palette()

    background = (4, 17, 27)
    cell_color = (12, 48, 66)
    sheet = Image.new("RGB", SHEET_SIZE, background)
    draw = ImageDraw.Draw(sheet)
    draw.text((28, 18), "2A v6 - tone-on-tone stonewash + Atkinson", font=font(28, True), fill=(255, 228, 151))
    draw.text(
        (28, 57),
        "Exact RD 82521 stone; 26 permanent tints stay inside one weathered clay, lichen, sea-glass and slate family.",
        font=font(13), fill=(151, 188, 198),
    )
    draw.text(
        (28, 85),
        "Atkinson Hyperlegible Next ExtraBold 800 is centered; every mineral plane now follows the card tint with no cyan or navy artifacts.",
        font=font(13), fill=(219, 237, 240),
    )

    for index, base565 in enumerate(palette):
        row, column = divmod(index, 6)
        cell_x = 32 + column * 176
        cell_y = 126 + row * 232
        draw.rounded_rectangle((cell_x, cell_y, cell_x + 160, cell_y + 222),
                               radius=12, fill=cell_color)
        card = render_card(renderer, role_image, index, base565)
        alpha = card.getchannel("A")
        # Center the 138 px card body exactly in the 160 px review cell. The
        # shadow retains the shipping three-by-six offset behind that center.
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
        "purpose": "Review-only combined 2A tone-on-tone stonewashed cards with selected Atkinson letter face.",
        "production_asset": False,
        "openai_image_generation_used": False,
        "new_generation_calls": 0,
        "source_rd_png": str(SOURCE.relative_to(ROOT)),
        "source_rd_sha256": SOURCE_SHA256,
        "source_alpha_bbox": list(SOURCE_BBOX),
        "selected_font": "Atkinson Hyperlegible Next ExtraBold 800",
        "selected_font_source_sha256": ATKINSON_SOURCE_SHA256,
        "selected_font_header": str(renderer.FONT_HEADER.relative_to(ROOT)),
        "selected_font_header_sha256": renderer.FONT_HEADER_SHA256,
        "card_renderer": str(PREVIEW_RENDERER.relative_to(ROOT)),
        "card_renderer_sha256": sha256(PREVIEW_RENDERER),
        "palette_strategy": "hand-tuned low-saturation clay, lichen, sage, sea-glass, slate, heather, and ochre family",
        "role_color_policy": "all eight visible RD semantic regions are narrow lightness steps derived from each letter base; no fixed cyan or navy texture colors",
        "fixed_elements": [
            "RD 82521 alpha silhouette and all eight semantic regions",
            "tone-on-tone mineral planes, chips, cracks, and glints",
            "letter-derived seed, 13 anchors, and four motif families",
            "exact checked-in Atkinson ExtraBold 800 one-bit glyph bitmap",
            "firmware integer sampling and motif raster order",
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
