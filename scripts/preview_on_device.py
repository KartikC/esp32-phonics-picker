#!/usr/bin/env python3
"""Render a pixel-faithful idle phonics round and optionally send it to AMOLED."""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
FONT_HEADER = ROOT / (
    "firmware/PhonicsGame/fonts/AtkinsonHyperlegibleNextExtraBold112.h"
)
REPLAY_SOURCE = ROOT / (
    "art/generated/one_off/replay_button_rd_native64_2026-08-25/"
    "retrodiffusion/native64_deep__82563.png"
)
STONE_SOURCE = ROOT / (
    "art/generated/one_off/letter_card_surfaces_2026-08-25/"
    "retrodiffusion/option2_carved_tide_stone__82521.png"
)
STONE_SOURCE_SHA256 = "80bb7f65419280532000c5399e159334f607a9087b67dbf31adc53e62da9b0df"
REPLAY_SOURCE_SHA256 = "33badbf1df0a9035a86e611eca44715dafbe1bf5c4b5390b0b20ea8d1f4dd97f"
FONT_HEADER_SHA256 = "18530ac78dbd2b366693e63e0ea69fd13556534b72ffa0afcbf456aac88e3c7d"
STONE_BBOX = (20, 7, 108, 120)
STONE_ROLE_RGB = {
    (95, 143, 160): "main_body",
    (53, 103, 122): "body_shadow",
    (11, 42, 60): "deep_crevice",
    (216, 238, 240): "pale_mineral",
    (18, 74, 96): "deep_slate",
    (145, 183, 190): "mid_mineral",
    (247, 255, 255): "white_chip",
    (39, 211, 208): "cyan_glint",
}
WIDTH, HEIGHT = 368, 448
COLORS_565 = [
    0x8B0A, 0x5BCD, 0x732F, 0x7BC9, 0x536F, 0x830D, 0x5BAB,
    0x6B10, 0x8B89, 0x53CE, 0x7AEE, 0x6BA9, 0x5B70, 0x8AEA,
    0x53AB, 0x62F0, 0x83A9, 0x53AF, 0x82ED, 0x5BCA, 0x72F0,
    0x8B09, 0x5BAD, 0x72EF, 0x73C9, 0x5370,
]
LAYOUTS = [(0, 0, 0, 6), (-7, 7, 5, -2), (5, -4, -7, 7),
           (-3, -6, 7, 3), (7, 4, -4, -5), (-5, 2, 4, 8)]


def rgb565(value: int) -> tuple[int, int, int]:
    return (((value >> 11) & 31) * 255 // 31,
            ((value >> 5) & 63) * 255 // 63,
            (value & 31) * 255 // 31)


def pack565(red: int, green: int, blue: int) -> int:
    return ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)


def blend565(foreground: int, background: int, amount: int) -> int:
    fr, fg, fb = (foreground >> 11) & 31, (foreground >> 5) & 63, foreground & 31
    br, bg, bb = (background >> 11) & 31, (background >> 5) & 63, background & 31
    red = (fr * amount + br * (255 - amount)) // 255
    green = (fg * amount + bg * (255 - amount)) // 255
    blue = (fb * amount + bb * (255 - amount)) // 255
    return (red << 11) | (green << 5) | blue


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def role_palette(base565: int) -> dict[str, int]:
    main = blend565(base565, 0x0000, 199)
    return {
        "main_body": main,
        "body_shadow": blend565(main, 0x0000, 217),
        "deep_crevice": blend565(main, 0x0000, 178),
        "pale_mineral": blend565(main, 0xFFFF, 225),
        "deep_slate": blend565(main, 0x0000, 204),
        "mid_mineral": blend565(main, 0xFFFF, 242),
        "white_chip": blend565(main, 0xFFFF, 204),
        "cyan_glint": blend565(main, 0xFFFF, 230),
    }


def letter_anchors(letter: str, width: int, height: int) -> list[tuple[int, int]]:
    state = 0x9E3779B9 ^ ((ord(letter) - ord("a") + 1) * 0x45D9F3B)
    anchors = []
    for _ in range(13):
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        x = 17 + ((state >> 8) % (width - 34))
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        y = 18 + ((state >> 8) % (height - 36))
        anchors.append((x, y))
    return anchors


def embedded_glyph(letter: str) -> Image.Image:
    """Decode the exact one-bit GFX glyph checked into the firmware."""
    source = FONT_HEADER.read_text()
    bitmap_block = re.search(
        r"AtkinsonHyperlegibleNextExtraBold112Bitmaps\[\].*?=\s*\{(.*?)\};",
        source, re.DOTALL,
    )
    glyph_block = re.search(
        r"AtkinsonHyperlegibleNextExtraBold112Glyphs\[\].*?=\s*\{(.*?)\};",
        source, re.DOTALL,
    )
    if not bitmap_block or not glyph_block:
        raise SystemExit("could not decode the checked-in Atkinson font header")
    bitmap = bytes(
        int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]{2})", bitmap_block.group(1))
    )
    glyphs = {}
    for match in re.finditer(
        r"\{\s*(\d+),\s*(\d+),\s*(\d+),\s*\d+,\s*-?\d+,\s*-?\d+\s*\}"
        r"\s*,?\s*//\s*0x([0-9A-Fa-f]{2})",
        glyph_block.group(1),
    ):
        offset, width, height, codepoint = (
            int(match.group(1)), int(match.group(2)), int(match.group(3)),
            int(match.group(4), 16),
        )
        glyphs[chr(codepoint)] = (offset, width, height)
    if letter not in glyphs:
        raise SystemExit(f"letter {letter!r} is missing from the embedded font")
    offset, width, height = glyphs[letter]
    glyph = Image.new("L", (width, height), 0)
    for bit_index in range(width * height):
        if bitmap[offset + bit_index // 8] & (0x80 >> (bit_index & 7)):
            glyph.putpixel((bit_index % width, bit_index // width), 255)
    return glyph


def motif_pixel(surface: Image.Image, main_body: list[list[bool]],
                x: int, y: int, color: tuple[int, int, int, int]) -> None:
    if 0 <= y < len(main_body) and 0 <= x < len(main_body[0]) and main_body[y][x]:
        surface.putpixel((x, y), color)


def motif_line(surface: Image.Image, main_body: list[list[bool]],
               x0: int, y0: int, x1: int, y1: int,
               color: tuple[int, int, int, int]) -> None:
    dx = abs(x1 - x0)
    step_x = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    step_y = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        motif_pixel(surface, main_body, x0, y0, color)
        if x0 == x1 and y0 == y1:
            break
        doubled = error * 2
        if doubled >= dy:
            error += dy
            x0 += step_x
        if doubled <= dx:
            error += dx
            y0 += step_y


def motif_shape(surface: Image.Image, main_body: list[list[bool]],
                family: int, index: int, x: int, y: int,
                color: tuple[int, int, int, int]) -> None:
    if family == 0:
        radius = 2 + index % 2
        for delta_y in range(-radius, radius + 1):
            for delta_x in range(-radius, radius + 1):
                if delta_x * delta_x + delta_y * delta_y <= radius * radius:
                    motif_pixel(surface, main_body, x + delta_x, y + delta_y, color)
        motif_pixel(surface, main_body, x + 4, y - 3, color)
    elif family == 1:
        motif_line(surface, main_body, x - 4, y + 3, x + 4, y - 3, color)
        motif_line(surface, main_body, x - 2, y + 4, x + 5, y - 1, color)
    elif family == 2:
        motif_line(surface, main_body, x - 3, y, x + 3, y, color)
        motif_line(surface, main_body, x, y - 3, x, y + 3, color)
        motif_pixel(surface, main_body, x + 4, y + 3, color)
    else:
        motif_line(surface, main_body, x - 2, y - 2, x + 2, y - 2, color)
        motif_line(surface, main_body, x + 2, y - 2, x + 2, y + 2, color)
        motif_line(surface, main_body, x + 2, y + 2, x - 2, y + 2, color)
        motif_line(surface, main_body, x - 2, y + 2, x - 2, y - 2, color)
        motif_pixel(surface, main_body, x + 4, y - 3, color)


def shifted_mask(mask: Image.Image, dx: int, dy: int) -> Image.Image:
    shifted = Image.new("L", mask.size, 0)
    shifted.paste(mask, (dx, dy))
    return shifted


def card(image: Image.Image, letter: str, rect: tuple[int, int, int, int],
         stone_source: Image.Image) -> None:
    x, y, w, h = rect
    colors = role_palette(COLORS_565[ord(letter) - ord("a")])
    surface = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    main_body = [[False for _ in range(w)] for _ in range(h)]
    for local_y in range(h):
        source_y = local_y * stone_source.height // h
        for local_x in range(w):
            source_x = local_x * stone_source.width // w
            rgba = stone_source.getpixel((source_x, source_y))
            if rgba[3] == 0:
                continue
            role = STONE_ROLE_RGB[rgba[:3]]
            surface.putpixel((local_x, local_y), (*rgb565(colors[role]), 255))
            if role == "main_body":
                main_body[local_y][local_x] = True

    light = (*rgb565(blend565(
        colors["main_body"], colors["pale_mineral"], 230)), 255)
    dark = (*rgb565(blend565(colors["main_body"], 0x0000, 214)), 255)
    family = (ord(letter) - ord("a")) % 4
    for index, (anchor_x, anchor_y) in enumerate(letter_anchors(letter, w, h)):
        motif_shape(surface, main_body, family, index,
                    anchor_x - 1, anchor_y - 1, light)
        motif_shape(surface, main_body, family, index,
                    anchor_x, anchor_y, dark)

    glyph = embedded_glyph(letter)
    glyph_mask = Image.new("L", (w, h), 0)
    glyph_mask.paste(glyph, (w // 2 - glyph.width // 2,
                             h // 2 - glyph.height // 2))
    halo_mask = Image.new("L", (w, h), 0)
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        halo_mask = ImageChops.lighter(halo_mask, shifted_mask(glyph_mask, dx, dy))
    surface.paste((*rgb565(pack565(11, 42, 60)), 255),
                  (0, 0, w, h), halo_mask)
    surface.paste((255, 255, 255, 255), (0, 0, w, h), glyph_mask)

    alpha = surface.getchannel("A")
    shadow = Image.new("RGBA", (w, h), (*rgb565(0x0042), 255))
    image.paste(shadow, (x + 3, y + 6), alpha)
    image.paste(surface, (x, y), surface)


def battery_indicator(draw, percent):
    if percent is None:
        return
    tier = 3 if percent >= 60 else 2 if percent >= 25 else 1
    source = 0x07E0 if tier == 3 else 0xFFE0 if tier == 2 else 0xF800
    amount = 145 if tier == 3 else 155 if tier == 2 else 175
    color = rgb565(blend565(source, 0x0000, amount))
    center_x, center_y, spacing = WIDTH // 2, 14, 11
    first_x = center_x - ((tier - 1) * spacing) // 2
    for index in range(tier):
        x = first_x + index * spacing
        draw.ellipse((x - 3, center_y - 3, x + 3, center_y + 3), fill=color)


def make_frame(left, right, layout, battery, muted=False):
    image = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(image)
    stone = Image.open(STONE_SOURCE).convert("RGBA").crop(STONE_BBOX)
    replay_source = Image.open(REPLAY_SOURCE).convert("RGBA")
    replay = Image.new("RGBA", replay_source.size, (0, 0, 0, 0))
    for point in ((x, y) for y in range(replay.height) for x in range(replay.width)):
        rgba = replay_source.getpixel(point)
        if rgba[3]:
            replay.putpixel(point, (*rgb565(pack565(*rgba[:3])), 255))
    image.paste(replay, (152, 28), replay)
    if muted:
        slash = rgb565(pack565(232, 72, 72))
        draw.line((162, 38, 206, 82), fill=slash)
        draw.line((163, 38, 207, 82), fill=slash)
    battery_indicator(draw, battery)
    lx, ly, rx, ry = LAYOUTS[layout]
    card(image, left, (32 + lx, 206 + ly, 138, 158), stone)
    card(image, right, (195 + rx, 206 + ry, 138, 158), stone)
    return image


def to_rgb565_bytes(image):
    output = bytearray()
    for red, green, blue in image.getdata():
        value = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
        output.extend(struct.pack("<H", value))
    return bytes(output)


def main():
    def battery_value(value: str) -> int | None:
        if value.lower() in {"none", "off", "hidden"}:
            return None
        percent = int(value)
        if not 0 <= percent <= 100:
            raise argparse.ArgumentTypeError("battery must be 0-100 or 'none'")
        return percent

    parser = argparse.ArgumentParser()
    parser.add_argument("--left", default="a", choices=list("abcdefghijklmnopqrstuvwxyz"))
    parser.add_argument("--right", default="m", choices=list("abcdefghijklmnopqrstuvwxyz"))
    parser.add_argument("--layout", type=int, default=0, choices=range(6))
    parser.add_argument("--battery", type=battery_value, default=50)
    parser.add_argument(
        "--muted", action="store_true",
        help="show the USB-data-attached maintenance-mute slash",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "previews/latest.png")
    parser.add_argument("--port")
    args = parser.parse_args()
    if args.left == args.right:
        raise SystemExit("preview choices must be different letters")
    for path, expected in (
        (STONE_SOURCE, STONE_SOURCE_SHA256),
        (REPLAY_SOURCE, REPLAY_SOURCE_SHA256),
        (FONT_HEADER, FONT_HEADER_SHA256),
    ):
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"reviewed preview source is missing or changed: {path}")
    image = make_frame(args.left, args.right, args.layout, args.battery, args.muted)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)
    print(args.output)
    if args.port:
        import serial
        with serial.Serial(args.port, 115200, timeout=8, write_timeout=8) as device:
            device.write(b"FRAME\n")
            device.write(to_rgb565_bytes(image))
            device.flush()
            print(device.readline().decode("utf-8", "replace").strip())


if __name__ == "__main__":
    main()
