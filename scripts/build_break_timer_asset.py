#!/usr/bin/env python3
"""Build the selected native Retro Diffusion tideglass for firmware."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, deque
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / (
    "art/generated/one_off/break_timer_rd_native128_2026-08-28/"
    "retrodiffusion/tideglass_shell__82802.png"
)
METADATA = SOURCE.with_suffix(".json")
GENERATION_SUMMARY = ROOT / (
    "art/generated/one_off/break_timer_rd_native128_2026-08-28/"
    "generation_summary.json"
)
GENERATOR = GENERATION_SUMMARY.parent / "generate.py"
TASKS = GENERATION_SUMMARY.parent / "tasks.json"
CONTACT_SHEET = GENERATION_SUMMARY.parent / "contact_sheet.png"
HEADER = ROOT / "firmware/PhonicsGame/BreakTimerAsset.h"
REPORT = ROOT / "art/break_timer/generated/tideglass_report.json"
PREVIEW_RENDERER = ROOT / "scripts/preview_break_timer.py"

SOURCE_SHA256 = "a47483a3503dc8615ae95a0797677ac0a14cd2fcf938a2f19fdfa181632d0b83"
METADATA_SHA256 = "18c75543bf65415507781a88a9502168350fa00bb2f20c4e5d82134120d4373b"
SOURCE_SIZE = (128, 128)
ALPHA_BBOX = (23, 1, 105, 128)
SEED = 82802
TASK_ID = "58783246-31be-4cac-bafc-9226bd75ee44"

# Transparent plus the exact nine opaque colors returned by Retro Diffusion.
ROLE_RGB = (
    None,
    (7, 21, 34),
    (11, 42, 60),
    (18, 74, 96),
    (53, 103, 122),
    (95, 143, 160),
    (145, 183, 190),
    (216, 238, 240),
    (242, 181, 107),
    (244, 227, 155),
)
EXPECTED_COUNTS = (8306, 1885, 283, 1338, 2280, 506, 152, 316, 1313, 5)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rgb565(rgb: tuple[int, int, int]) -> int:
    red, green, blue = rgb
    return ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)


def fail(message: str) -> None:
    raise RuntimeError(message)


def validate_metadata() -> dict:
    if sha256(SOURCE) != SOURCE_SHA256:
        fail("selected tideglass PNG hash changed")
    if sha256(METADATA) != METADATA_SHA256:
        fail("selected tideglass metadata hash changed")
    metadata = json.loads(METADATA.read_text())
    expected = {
        "vendor": "retrodiffusion",
        "asset_id": "tideglass_shell",
        "label": "2 - Shell-inlay glass",
        "seed": SEED,
        "task_id": TASK_ID,
        "prompt_style": "rd_pro__simple",
        "source_size": list(SOURCE_SIZE),
        "source_mode": "RGBA",
        "alpha_bbox": list(ALPHA_BBOX),
        "alpha_values": [0, 255],
        "corner_transparency_gate_passed": True,
        "png_sha256": SOURCE_SHA256,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            fail(f"selected tideglass metadata has invalid {key}")
    if metadata.get("response", {}).get("model") != "rd_pro":
        fail("selected tideglass metadata has the wrong provider model")
    return metadata


def connected_pixels(pixels: set[tuple[int, int]]) -> int:
    if not pixels:
        return 0
    pending = deque([next(iter(pixels))])
    visited = {pending[0]}
    while pending:
        x, y = pending.popleft()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor in pixels and neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    return len(visited)


def semantic_pixels() -> tuple[list[int], Counter[int]]:
    image = Image.open(SOURCE).convert("RGBA")
    if image.size != SOURCE_SIZE or image.getchannel("A").getbbox() != ALPHA_BBOX:
        fail("selected tideglass dimensions or alpha bounds changed")
    by_rgb = {color: role for role, color in enumerate(ROLE_RGB) if color}
    roles: list[int] = []
    opaque: set[tuple[int, int]] = set()
    for y in range(image.height):
        for x in range(image.width):
            rgba = image.getpixel((x, y))
            if rgba[3] == 0:
                roles.append(0)
            elif rgba[3] == 255 and rgba[:3] in by_rgb:
                roles.append(by_rgb[rgba[:3]])
                opaque.add((x, y))
            else:
                fail(f"unexpected tideglass pixel {rgba} at {x},{y}")
    if connected_pixels(opaque) != len(opaque):
        fail("selected tideglass contains detached opaque pixels")
    counts = Counter(roles)
    if tuple(counts[index] for index in range(len(ROLE_RGB))) != EXPECTED_COUNTS:
        fail("selected tideglass semantic pixel counts changed")
    for corner in ((0, 0), (127, 0), (0, 127), (127, 127)):
        if roles[corner[1] * SOURCE_SIZE[0] + corner[0]] != 0:
            fail("selected tideglass canvas corner is opaque")
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

// Untouched Retro Diffusion rd_pro Shell-inlay tideglass, seed {SEED},
// packed as an exact native 128x128 indexed image. Transparent pixels remain
// the physically black AMOLED background; the artwork is never resized.
inline constexpr uint16_t kBreakTimerWidth = 128;
inline constexpr uint16_t kBreakTimerHeight = 128;
inline constexpr uint16_t kBreakTimerPackedBytes = 8192;
inline constexpr uint16_t kBreakTimerOpaquePixels = 8078;
inline constexpr uint16_t kBreakTimerAlphaLeft = 23;
inline constexpr uint16_t kBreakTimerAlphaTop = 1;
inline constexpr uint16_t kBreakTimerAlphaRight = 105;
inline constexpr uint16_t kBreakTimerAlphaBottom = 128;
inline constexpr uint8_t kBreakTimerTransparent = 0;
inline constexpr uint8_t kBreakTimerSand = 8;
inline constexpr uint8_t kBreakTimerSandHighlight = 9;

inline constexpr uint16_t kBreakTimerPalette[10] = {{
{format_values([f"0x{value:04X}" for value in palette], 10)}
}};

inline constexpr uint16_t kBreakTimerRolePixelCounts[10] = {{
{format_values([f"{counts[index]}u" for index in range(10)], 10)}
}};

inline const uint8_t kBreakTimerPackedRoles[kBreakTimerPackedBytes]
    PROGMEM = {{
{format_values([f"0x{value:02X}" for value in packed], 16)}
}};

inline uint8_t breakTimerRoleAt(uint16_t x, uint16_t y) {{
  const uint32_t index = static_cast<uint32_t>(y) * kBreakTimerWidth + x;
  const uint8_t packed = kBreakTimerPackedRoles[index >> 1];
  return (index & 1u) ? static_cast<uint8_t>(packed >> 4)
                      : static_cast<uint8_t>(packed & 0x0fu);
}}

}}  // namespace phonics_game
"""


def selection_evidence(generation: dict) -> list[dict[str, str]]:
    paths = [GENERATOR, TASKS, GENERATION_SUMMARY, CONTACT_SHEET]
    samples = generation.get("samples", [])
    if len(samples) != 3:
        fail("break-timer generation summary must contain three candidates")
    for sample in samples:
        png = ROOT / sample["png"]
        paths.extend((png, png.with_suffix(".json")))
    evidence = []
    for path in paths:
        if not path.is_file():
            fail(f"break-timer selection evidence is missing: {path}")
        evidence.append({
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
        })
    return evidence


def main() -> None:
    metadata = validate_metadata()
    roles, counts = semantic_pixels()
    packed = pack_nibbles(roles)
    HEADER.write_text(build_header(packed, counts))
    generation = json.loads(GENERATION_SUMMARY.read_text())
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "status": "passed",
        "selected_direction": "2 - Shell-inlay glass",
        "selection_reason": (
            "clearest complete child-readable tideglass at device scale; "
            "transparent corners and one connected opaque component"
        ),
        "rejected_directions": [
            {
                "label": "1 - Tide-stone glass",
                "reason": "side pillars read as a separate gate and weaken the hourglass silhouette",
            },
            {
                "label": "3 - Deep-current glass",
                "reason": "failed the transparent-corner gate and is visibly cropped",
            },
        ],
        "production_asset": True,
        "vendor": "retrodiffusion",
        "provider_model": "rd_pro",
        "prompt_style": "rd_pro__simple",
        "seed": SEED,
        "task_id": TASK_ID,
        "provider_reported_balance_cost": metadata["response"]["balance_cost"],
        "candidate_generation_calls": generation["generation_call_count"],
        "candidate_generation_balance_cost_total": generation[
            "retrodiffusion_reported_balance_cost_total"
        ],
        "selection_evidence": selection_evidence(generation),
        "openai_image_generation_used": False,
        "usage_rights": "not recorded locally; consult Retro Diffusion provider terms",
        "postprocess": "none before deterministic indexed packing",
        "builder": str(Path(__file__).resolve().relative_to(ROOT)),
        "builder_sha256": sha256(Path(__file__).resolve()),
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": SOURCE_SHA256,
        "source_metadata": str(METADATA.relative_to(ROOT)),
        "source_metadata_sha256": METADATA_SHA256,
        "source_size": list(SOURCE_SIZE),
        "alpha_bbox": list(ALPHA_BBOX),
        "accepted_edge_contact": "bottom frame reaches row 127 but is visually complete",
        "opaque_pixels": sum(counts[index] for index in range(1, 10)),
        "transparent_pixels": counts[0],
        "connected_opaque_components": 1,
        "packed_bytes": len(packed),
        "packed_sha256": hashlib.sha256(packed).hexdigest(),
        "header": str(HEADER.relative_to(ROOT)),
        "header_sha256": sha256(HEADER),
        "preview_renderer": str(PREVIEW_RENDERER.relative_to(ROOT)),
        "preview_renderer_sha256": sha256(PREVIEW_RENDERER),
        "palette_rgb565": [
            "0x0000", *[f"0x{rgb565(color):04X}" for color in ROLE_RGB[1:]]
        ],
        "role_pixel_counts": [counts[index] for index in range(10)],
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {HEADER.relative_to(ROOT)} ({len(packed)} packed bytes)")
    print(f"Wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        raise SystemExit(f"break-timer asset build failed: {error}")
