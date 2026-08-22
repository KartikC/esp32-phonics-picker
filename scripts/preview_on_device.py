#!/usr/bin/env python3
"""Render a phonics frame on the Mac and optionally send it to the AMOLED."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT_ROOT = Path("/Users/kartiksathappan/Documents/ChatGPT/Letterboard/android/app/src/main/res/font")
WIDTH, HEIGHT = 368, 448
COLORS_565 = [
    0x934A, 0x1B6A, 0x63C8, 0x93A3, 0x2B4A, 0x8B4A, 0x13A9,
    0x8364, 0x3B88, 0x9345, 0x238B, 0x7323, 0x538A, 0x9325,
    0x1387, 0x6B68, 0x7B23, 0x2B8B, 0x9328, 0x1B85, 0x8B66,
    0x43AA, 0x9323, 0x138A, 0x7B46, 0x6B43,
]
LAYOUTS = [(0, 0, 0, 6), (-7, 7, 5, -2), (5, -4, -7, 7),
           (-3, -6, 7, 3), (7, 4, -4, -5), (-5, 2, 4, 8)]


def rgb565(value: int) -> tuple[int, int, int]:
    return (((value >> 11) & 31) * 255 // 31,
            ((value >> 5) & 63) * 255 // 63,
            (value & 31) * 255 // 31)


def blend(fg, bg, amount):
    return tuple((f * amount + b * (255 - amount)) // 255 for f, b in zip(fg, bg))


def lcg(value):
    return (value * 1664525 + 1013904223) & 0xFFFFFFFF


def card(draw, letter, rect, font):
    x, y, w, h = rect
    base = rgb565(COLORS_565[ord(letter) - 97])
    fill = blend(base, rgb565(0x1108), 205)
    draw.rounded_rectangle((x + 3, y + 6, x + w + 3, y + h + 6), 20, fill=rgb565(0x0204))
    draw.rounded_rectangle((x, y, x + w, y + h), 20, fill=fill,
                           outline=blend((255, 255, 255), base, 145), width=1)
    draw.line((x + 22, y + 11, x + w - 22, y + 11),
              fill=blend((255, 255, 255), base, 165))
    texture = blend((255, 255, 255), base, 34)
    state = (0x9E3779B9 ^ ((ord(letter) - 96) * 0x45D9F3B)) & 0xFFFFFFFF
    for i in range(13):
        state = lcg(state); px = x + 17 + ((state >> 8) % (w - 34))
        state = lcg(state); py = y + 18 + ((state >> 8) % (h - 36))
        style = (ord(letter) - 97) % 4
        if style == 0:
            r = 2 + i % 2; draw.ellipse((px-r, py-r, px+r, py+r), fill=texture)
        elif style == 1:
            draw.line((px-4, py+3, px+4, py-3), fill=texture)
        elif style == 2:
            draw.line((px-3, py, px+3, py), fill=texture)
            draw.line((px, py-3, px, py+3), fill=texture)
        else:
            draw.rectangle((px-2, py-2, px+2, py+2), outline=texture)
    box = font.getbbox(letter, anchor="ls")
    bx = x + w / 2 - (box[0] + box[2]) / 2
    by = y + h / 2 - (box[1] + box[3]) / 2
    shadow = blend((0, 0, 0), base, 165)
    # Use a one-bit native-size mask to match the embedded renderer exactly.
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        draw.text((bx + dx, by + dy), letter, font=font, anchor="ls", fill=shadow,
                  stroke_width=0)
    draw.text((bx, by), letter, font=font, anchor="ls", fill="white")


def make_frame(left, right, layout):
    image = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(image)
    letter_font = ImageFont.truetype(str(FONT_ROOT / "nunito_black.ttf"), 112)
    guide_font = ImageFont.truetype(str(FONT_ROOT / "nunito_bold.ttf"), 28)
    moon = rgb565(0xEF5C)
    draw.text((WIDTH / 2, 87), "listen", font=guide_font, anchor="mm", fill=moon)
    draw.ellipse((154, 109, 214, 169), outline=moon)
    draw.polygon(((174, 130), (174, 148), (194, 139)), fill=moon)
    draw.text((WIDTH / 2, 190), "pick one", font=guide_font, anchor="mm", fill=moon)
    lx, ly, rx, ry = LAYOUTS[layout]
    card(draw, left, (22 + lx, 220 + ly, 145, 158), letter_font)
    card(draw, right, (201 + rx, 220 + ry, 145, 158), letter_font)
    return image


def to_rgb565_bytes(image):
    output = bytearray()
    for red, green, blue in image.getdata():
        value = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
        output.extend(struct.pack("<H", value))
    return bytes(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", default="a", choices=list("abcdefghijklmnopqrstuvwxyz"))
    parser.add_argument("--right", default="m", choices=list("abcdefghijklmnopqrstuvwxyz"))
    parser.add_argument("--layout", type=int, default=0, choices=range(6))
    parser.add_argument("--output", type=Path, default=ROOT / "previews/latest.png")
    parser.add_argument("--port")
    args = parser.parse_args()
    if args.left == args.right:
        raise SystemExit("preview choices must be different letters")
    image = make_frame(args.left, args.right, args.layout)
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
