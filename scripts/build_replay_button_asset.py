#!/usr/bin/env python3
"""Build the selected native Deep loop replay button for the firmware."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, deque
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / (
    "art/generated/one_off/replay_button_rd_native64_2026-08-25/"
    "retrodiffusion/native64_deep__82563.png"
)
METADATA = SOURCE.with_suffix(".json")
HEADER = ROOT / "firmware/PhonicsGame/ReplayButtonAsset.h"
REPORT = ROOT / "art/replay_button/generated/deep_loop_report.json"

SOURCE_SHA256 = "33badbf1df0a9035a86e611eca44715dafbe1bf5c4b5390b0b20ea8d1f4dd97f"
METADATA_SHA256 = "98cdbddb1fb07d9abc9588888cfee6cd9a8436c9ce7ab22f0f8aaf290a6d2833"
SOURCE_SIZE = (64, 64)
ALPHA_BBOX = (1, 1, 63, 63)
PLAY_GLYPH_BBOX = (24, 19, 46, 45)
SEED = 82563

# Transparent plus the exact eight opaque colors returned by Retro Diffusion.
ROLE_RGB = (
    None,
    (7, 21, 34),
    (11, 42, 60),
    (18, 74, 96),
    (53, 103, 122),
    (95, 143, 160),
    (145, 183, 190),
    (216, 238, 240),
    (247, 255, 255),
)
EXPECTED_COUNTS = (1072, 539, 2, 922, 590, 4, 1, 637, 329)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rgb565(rgb: tuple[int, int, int]) -> int:
    red, green, blue = rgb
    return ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)


def fail(message: str) -> None:
    raise RuntimeError(message)


def validate_metadata() -> dict:
    if sha256(SOURCE) != SOURCE_SHA256:
        fail("selected Deep loop PNG hash changed")
    if sha256(METADATA) != METADATA_SHA256:
        fail("selected Deep loop metadata hash changed")
    metadata = json.loads(METADATA.read_text())
    expected = {
        "vendor": "retrodiffusion",
        "asset_id": "native64_deep",
        "label": "3 - Deep loop",
        "seed": SEED,
        "prompt_style": "rd_pro__simple",
        "source_size": list(SOURCE_SIZE),
        "source_mode": "RGBA",
        "alpha_bbox": list(ALPHA_BBOX),
        "corner_transparency_gate_passed": True,
        "png_sha256": SOURCE_SHA256,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            fail(f"selected Deep loop metadata has invalid {key}")
    if metadata.get("response", {}).get("model") != "rd_pro":
        fail("selected Deep loop metadata has the wrong provider model")
    return metadata


def connected_opaque_pixels(opaque: set[tuple[int, int]]) -> int:
    if not opaque:
        return 0
    pending = deque([next(iter(opaque))])
    visited = {pending[0]}
    while pending:
        x, y = pending.popleft()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor in opaque and neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    return len(visited)


def semantic_pixels() -> tuple[list[int], Counter[int]]:
    image = Image.open(SOURCE).convert("RGBA")
    if image.size != SOURCE_SIZE or image.getchannel("A").getbbox() != ALPHA_BBOX:
        fail("selected Deep loop dimensions or alpha bounds changed")
    by_rgb = {color: role for role, color in enumerate(ROLE_RGB) if color}
    roles: list[int] = []
    opaque: set[tuple[int, int]] = set()
    play_glyph: set[tuple[int, int]] = set()
    for y in range(image.height):
        for x in range(image.width):
            rgba = image.getpixel((x, y))
            if rgba[3] == 0:
                roles.append(0)
            elif rgba[3] == 255 and rgba[:3] in by_rgb:
                roles.append(by_rgb[rgba[:3]])
                opaque.add((x, y))
                if by_rgb[rgba[:3]] == 8:
                    play_glyph.add((x, y))
            else:
                fail(f"unexpected Deep loop pixel {rgba} at {x},{y}")
    if connected_opaque_pixels(opaque) != len(opaque):
        fail("selected Deep loop contains detached opaque pixels")
    if connected_opaque_pixels(play_glyph) != len(play_glyph):
        fail("selected Deep loop white play glyph is not one component")
    play_bbox = (
        min(x for x, _ in play_glyph), min(y for _, y in play_glyph),
        max(x for x, _ in play_glyph) + 1, max(y for _, y in play_glyph) + 1,
    )
    if play_bbox != PLAY_GLYPH_BBOX:
        fail("selected Deep loop white play-glyph bounds changed")
    counts = Counter(roles)
    if tuple(counts[index] for index in range(len(ROLE_RGB))) != EXPECTED_COUNTS:
        fail("selected Deep loop semantic pixel counts changed")
    return roles, counts


def pack_nibbles(roles: list[int]) -> bytes:
    packed = bytearray()
    for index in range(0, len(roles), 2):
        packed.append(roles[index] | (roles[index + 1] << 4))
    return bytes(packed)


def format_values(values: list[str], per_line: int) -> str:
    return "\n".join(
        "    " + ", ".join(values[index:index + per_line]) + ","
        for index in range(0, len(values), per_line)
    )


def build_header(packed: bytes, counts: Counter[int]) -> str:
    palette = [0x0000] + [rgb565(color) for color in ROLE_RGB[1:]]
    return f"""#pragma once

#include <stdint.h>

#ifndef PROGMEM
#define PROGMEM
#endif

namespace phonics_game {{

// Untouched Retro Diffusion rd_pro Deep loop, seed {SEED}, packed as an
// exact native 64x64 indexed image. Transparent pixels remain the physically
// black AMOLED background; the visible control is never resized or cropped.
inline constexpr uint16_t kReplayButtonWidth = 64;
inline constexpr uint16_t kReplayButtonHeight = 64;
inline constexpr uint16_t kReplayButtonPackedBytes = 2048;
inline constexpr uint16_t kReplayButtonOpaquePixels = 3024;
inline constexpr uint16_t kReplayButtonAlphaLeft = 1;
inline constexpr uint16_t kReplayButtonAlphaTop = 1;
inline constexpr uint16_t kReplayButtonAlphaRight = 63;
inline constexpr uint16_t kReplayButtonAlphaBottom = 63;
inline constexpr uint8_t kReplayButtonTransparent = 0;
inline constexpr uint8_t kReplayButtonFace = 3;
inline constexpr uint8_t kReplayButtonPlayGlyph = 8;
inline constexpr uint16_t kReplayButtonPlayLeft = 24;
inline constexpr uint16_t kReplayButtonPlayTop = 19;
inline constexpr uint16_t kReplayButtonPlayRight = 46;
inline constexpr uint16_t kReplayButtonPlayBottom = 45;

inline constexpr uint16_t kReplayButtonPalette[9] = {{
{format_values([f"0x{value:04X}" for value in palette], 9)}
}};

inline constexpr uint16_t kReplayButtonRolePixelCounts[9] = {{
{format_values([f"{counts[index]}u" for index in range(9)], 9)}
}};

inline const uint8_t kReplayButtonPackedRoles[kReplayButtonPackedBytes]
    PROGMEM = {{
{format_values([f"0x{value:02X}" for value in packed], 16)}
}};

inline uint8_t replayButtonRoleAt(uint16_t x, uint16_t y) {{
  const uint32_t index = static_cast<uint32_t>(y) * kReplayButtonWidth + x;
  const uint8_t packed = kReplayButtonPackedRoles[index >> 1];
  return (index & 1u) ? static_cast<uint8_t>(packed >> 4)
                      : static_cast<uint8_t>(packed & 0x0fu);
}}

}}  // namespace phonics_game
"""


def main() -> None:
    metadata = validate_metadata()
    roles, counts = semantic_pixels()
    packed = pack_nibbles(roles)
    HEADER.write_text(build_header(packed, counts))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "status": "passed",
        "selected_direction": "3 - Deep loop",
        "production_asset": True,
        "vendor": "retrodiffusion",
        "provider_model": "rd_pro",
        "prompt_style": "rd_pro__simple",
        "seed": SEED,
        "task_id": metadata["task_id"],
        "provider_reported_balance_cost": metadata["response"]["balance_cost"],
        "openai_image_generation_used": False,
        "new_generation_calls": 0,
        "postprocess": "none before deterministic indexed packing",
        "builder": str(Path(__file__).resolve().relative_to(ROOT)),
        "builder_sha256": sha256(Path(__file__).resolve()),
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": SOURCE_SHA256,
        "source_metadata": str(METADATA.relative_to(ROOT)),
        "source_metadata_sha256": METADATA_SHA256,
        "source_size": list(SOURCE_SIZE),
        "alpha_bbox": list(ALPHA_BBOX),
        "opaque_pixels": sum(counts[index] for index in range(1, 9)),
        "transparent_pixels": counts[0],
        "connected_opaque_components": 1,
        "connected_play_glyph_components": 1,
        "play_glyph_bbox": list(PLAY_GLYPH_BBOX),
        "packed_bytes": len(packed),
        "packed_sha256": hashlib.sha256(packed).hexdigest(),
        "header": str(HEADER.relative_to(ROOT)),
        "header_sha256": sha256(HEADER),
        "palette_rgb565": [
            "0x0000", *[f"0x{rgb565(color):04X}" for color in ROLE_RGB[1:]]
        ],
        "role_pixel_counts": [counts[index] for index in range(9)],
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {HEADER.relative_to(ROOT)} ({len(packed)} packed bytes)")
    print(f"Wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        raise SystemExit(f"replay-button asset build failed: {error}")
