#!/usr/bin/env python3
"""Regression checks for the source-faithful break-timer preview."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "preview_break_timer", ROOT / "scripts/preview_break_timer.py"
)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("could not load scripts/preview_break_timer.py")
PREVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIEW)


# Arduino_GFX clamps a one-pixel-wide rounded rectangle to radius zero. The
# center rectangle remains eight pixels tall and both ellipse helpers return.
single_pixel_bar = Image.new("RGB", (8, 12), "black")
PREVIEW.fill_round_rect(
    ImageDraw.Draw(single_pixel_bar), 3, 2, 1, 8, 4, (255, 255, 255)
)
assert (8, (255, 255, 255)) in single_pixel_bar.getcolors(maxcolors=96)

# Eight elapsed seconds is the first production countdown value whose integer
# progress calculation reaches that one-pixel path.
frame = PREVIEW.make_break_frame(1792, None)
assert frame.size == (PREVIEW.WIDTH, PREVIEW.HEIGHT)
assert frame.getpixel((64, 337)) == PREVIEW.rgb565(0xF713)
assert frame.getpixel((71, 337)) == PREVIEW.rgb565(0x0947)

# Pin source-faithful RGB565 frame output at the start, first one-pixel
# progress width, midpoint, and last displayed second.
expected_frames = {
    1800: "9bbe650cd1bb61b8db7fe079d9dfe3c65985c9e5c7fb488985cd481925052e64",
    1792: "2708353fcbc6cb24b5f64b742046c5f8b5b484083c811c981c7cde2535b99c7b",
    900: "3349b6c9926540925d6c70e80e34aed699bf8037bbae016842e76a0c6f3db523",
    1: "44b181d247df7b84ba8155ce283c9385075c81081207493bcd2d80b9aa460ee4",
}
for remaining_seconds, expected_sha256 in expected_frames.items():
    rendered = PREVIEW.make_break_frame(remaining_seconds, 50)
    assert hashlib.sha256(
        PREVIEW.to_rgb565_bytes(rendered)
    ).hexdigest() == expected_sha256

print("break_timer_preview_test passed")
