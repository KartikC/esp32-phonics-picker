#!/usr/bin/env python3
"""Render the source-faithful production break timer and optionally send it."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw

from preview_on_device import (
    HEIGHT,
    ROOT,
    WIDTH,
    battery_indicator,
    pack565,
    rgb565,
    sha256,
    to_rgb565_bytes,
)


BREAK_TIMER_SOURCE = ROOT / (
    "art/generated/one_off/break_timer_rd_native128_2026-08-28/"
    "retrodiffusion/tideglass_shell__82802.png"
)
GLCDFONT_HEADER = ROOT / "vendor/slim/GFX_Library_for_Arduino/src/font/glcdfont.h"
BREAK_TIMER_SOURCE_SHA256 = "a47483a3503dc8615ae95a0797677ac0a14cd2fcf938a2f19fdfa181632d0b83"


def classic_font_bytes() -> bytes:
    source = GLCDFONT_HEADER.read_text()
    block = re.search(r"font\[\].*?=\s*\{(.*?)\};", source, re.DOTALL)
    if not block:
        raise SystemExit("could not decode the checked-in classic GFX font")
    without_comments = re.sub(r"//.*", "", block.group(1))
    values = bytes(
        int(value, 16)
        for value in re.findall(r"0x([0-9A-Fa-f]{2})", without_comments)
    )
    if len(values) < 128 * 5:
        raise SystemExit("checked-in classic GFX font is incomplete")
    return values


def draw_centered_classic(draw: ImageDraw.ImageDraw, text: str,
                          center_x: int, center_y: int, scale: int,
                          color: tuple[int, int, int]) -> None:
    font = classic_font_bytes()
    width = len(text) * 6 * scale
    height = 8 * scale
    origin_x = center_x - width // 2
    origin_y = center_y - height // 2
    for character_index, character in enumerate(text):
        glyph = font[ord(character) * 5:ord(character) * 5 + 5]
        character_x = origin_x + character_index * 6 * scale
        for column, bits in enumerate(glyph):
            for row in range(8):
                if bits & (1 << row):
                    x = character_x + column * scale
                    y = origin_y + row * scale
                    draw.rectangle(
                        (x, y, x + scale - 1, y + scale - 1), fill=color
                    )


def fill_rect(draw: ImageDraw.ImageDraw, x: int, y: int, width: int,
              height: int, color: tuple[int, int, int]) -> None:
    if width > 0 and height > 0:
        draw.rectangle((x, y, x + width - 1, y + height - 1), fill=color)


def fill_ellipse_helper(draw: ImageDraw.ImageDraw, x: int, y: int,
                        radius_x: int, radius_y: int, corners: int,
                        delta: int, color: tuple[int, int, int]) -> None:
    """Port Arduino_GFX writeFillEllipseHelper for pixel-exact previews."""
    if (radius_x < 0 or radius_y < 0 or
            (radius_x == 0 and radius_y == 0)):
        return
    if radius_y == 0:
        fill_rect(draw, x - radius_x, y, (radius_y << 2) + 1, 1, color)
        return
    if radius_x == 0:
        fill_rect(draw, x, y - radius_y, 1, (radius_x << 2) + 1, color)
        return
    radius_x_squared = radius_x * radius_x
    radius_y_squared = radius_y * radius_y
    fill_rect(draw, x - radius_x, y, radius_x * 2 + 1, 1, color)

    previous = 0
    offset_y = 0
    offset_x = radius_x
    error = (radius_x_squared << 1) + radius_y_squared * (1 - (radius_x << 1))
    while True:
        while error < 0:
            offset_y += 1
            error += radius_x_squared * ((offset_y << 2) + 2)
        if corners & 1:
            fill_rect(draw, x - offset_x, y - offset_y,
                      (offset_x << 1) + 1 + delta,
                      offset_y - previous, color)
        if corners & 2:
            fill_rect(draw, x - offset_x, y + previous + 1,
                      (offset_x << 1) + 1 + delta,
                      offset_y - previous, color)
        previous = offset_y
        offset_x -= 1
        error -= (offset_x * radius_y_squared) << 2
        if radius_x_squared * offset_y > radius_y_squared * offset_x:
            break

    offset_x = 0
    offset_y = radius_y
    error = (radius_y_squared << 1) + radius_x_squared * (1 - (radius_y << 1))
    while True:
        while error < 0:
            offset_x += 1
            error += radius_y_squared * ((offset_x << 2) + 2)
        if corners & 1:
            fill_rect(draw, x - offset_x, y - offset_y,
                      (offset_x << 1) + 1 + delta, 1, color)
        if corners & 2:
            fill_rect(draw, x - offset_x, y + offset_y,
                      (offset_x << 1) + 1 + delta, 1, color)
        offset_y -= 1
        error -= (offset_y * radius_x_squared) << 2
        if radius_y_squared * offset_x > radius_x_squared * offset_y:
            break


def fill_round_rect(draw: ImageDraw.ImageDraw, x: int, y: int, width: int,
                    height: int, radius: int,
                    color: tuple[int, int, int]) -> None:
    radius = min(radius, min(width, height) // 2)
    fill_rect(draw, x, y + radius, width, height - 2 * radius, color)
    delta = width - 2 * radius - 1
    fill_ellipse_helper(draw, x + radius, y + radius,
                        radius, radius, 1, delta, color)
    fill_ellipse_helper(draw, x + radius, y + height - radius - 1,
                        radius, radius, 2, delta, color)


def fill_circle(draw: ImageDraw.ImageDraw, x: int, y: int, radius: int,
                color: tuple[int, int, int]) -> None:
    fill_ellipse_helper(draw, x, y, radius, radius, 3, 0, color)


def make_break_frame(remaining_seconds: int, battery: int | None) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "black")
    timer_source = Image.open(BREAK_TIMER_SOURCE).convert("RGBA")
    timer = Image.new("RGBA", timer_source.size, (0, 0, 0, 0))
    for point in ((x, y) for y in range(128) for x in range(128)):
        rgba = timer_source.getpixel(point)
        if rgba[3]:
            timer.putpixel(point, (*rgb565(pack565(*rgba[:3])), 255))
    image.paste(timer, (120, 54), timer)
    draw = ImageDraw.Draw(image)
    countdown = f"{remaining_seconds // 60:02d}:{remaining_seconds % 60:02d}"
    draw_centered_classic(draw, countdown, WIDTH // 2, 266, 7, rgb565(0xDF7E))

    fill_round_rect(draw, 64, 334, 240, 8, 4, rgb565(0x0947))
    remaining_ms = remaining_seconds * 1000
    progress = ((1800000 - remaining_ms) * 240) // 1800000
    if progress:
        fill_round_rect(draw, 64, 334, progress, 8, 4, rgb565(0xF713))
    pearl_x = 64 + (progress if progress < 240 else 239)
    fill_circle(draw, pearl_x, 338, 5, rgb565(0xF713))
    draw_centered_classic(draw, "rest", WIDTH // 2, 382, 3, rgb565(0x5C74))
    battery_indicator(draw, battery)
    return image


def main() -> None:
    def battery_value(value: str) -> int | None:
        if value.lower() in {"none", "off", "hidden"}:
            return None
        percent = int(value)
        if not 0 <= percent <= 100:
            raise argparse.ArgumentTypeError("battery must be 0-100 or 'none'")
        return percent

    parser = argparse.ArgumentParser()
    parser.add_argument("--remaining-seconds", type=int, default=1800,
                        choices=range(1, 1801))
    parser.add_argument("--battery", type=battery_value, default=50)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "previews/break-timer.png")
    parser.add_argument("--port")
    args = parser.parse_args()
    if (not BREAK_TIMER_SOURCE.is_file() or
            sha256(BREAK_TIMER_SOURCE) != BREAK_TIMER_SOURCE_SHA256):
        raise SystemExit("reviewed break-timer source is missing or changed")
    image = make_break_frame(args.remaining_seconds, args.battery)
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
