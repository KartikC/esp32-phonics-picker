#!/usr/bin/env python3
"""Turn approved external sprite candidates into an audited ESP32 creature pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import deque
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = Path(__file__).resolve()
CREATURE_ROOT = ROOT / "creatures"
MANIFEST_PATH = CREATURE_ROOT / "creature_manifest.json"
SELECTION_PATH = CREATURE_ROOT / "selection.json"
CANDIDATE_ROOT = CREATURE_ROOT / "generated" / "candidates"
PRODUCTION_ROOT = CREATURE_ROOT / "generated" / "production"
HEADER_PATH = ROOT / "firmware" / "OceanCreatureDemo" / "GeneratedCreatureSprites.h"
PRODUCTION_MANIFEST_PATH = PRODUCTION_ROOT / "production_manifest.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rgba_palette(manifest: dict) -> list[tuple[int, int, int, int]]:
    result = []
    for value in manifest["palette"]:
        if len(value) == 9:
            result.append(ImageColor.getcolor(value, "RGBA"))
        else:
            red, green, blue = ImageColor.getrgb(value)
            result.append((red, green, blue, 255))
    if len(result) != 16 or result[0][3] != 0:
        raise ValueError("manifest palette must contain 16 entries with transparent index zero")
    return result


def quantize_rgba(source: Image.Image, palette: list[tuple[int, int, int, int]]) -> Image.Image:
    source = source.convert("RGBA")
    target = Image.new("P", source.size, 0)
    output = []
    opaque_palette = palette[1:]
    for red, green, blue, alpha in source.get_flattened_data():
        if alpha < 128:
            output.append(0)
            continue
        best_index = min(
            range(len(opaque_palette)),
            key=lambda index: (
                (red - opaque_palette[index][0]) ** 2
                + (green - opaque_palette[index][1]) ** 2
                + (blue - opaque_palette[index][2]) ** 2
            ),
        )
        output.append(best_index + 1)
    target.putdata(output)
    return target


def indexed_to_rgba(indexed: Image.Image, palette: list[tuple[int, int, int, int]]) -> Image.Image:
    output = Image.new("RGBA", indexed.size, (0, 0, 0, 0))
    output.putdata([palette[value] for value in indexed.get_flattened_data()])
    return output


def normalize_candidate(source: Image.Image, asset: dict, palette: list[tuple[int, int, int, int]]) -> Image.Image:
    rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
    rgba.putalpha(alpha)
    bbox = alpha.getbbox()
    if not bbox:
        raise ValueError(f"{asset['id']} candidate has no opaque pixels")
    cropped = rgba.crop(bbox)
    content_width, content_height = asset["content_box"]
    scale = min(content_width / cropped.width, content_height / cropped.height)
    resized_size = (
        max(1, round(cropped.width * scale)),
        max(1, round(cropped.height * scale)),
    )
    resized = cropped.resize(resized_size, Image.Resampling.NEAREST)
    frame_width, frame_height = asset["target_size"]
    placed = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
    offset = ((frame_width - resized.width) // 2, (frame_height - resized.height) // 2)
    placed.alpha_composite(resized, offset)
    return quantize_rgba(placed, palette)


def shift_indexed(source: Image.Image, x_offset: int, y_offset: int) -> Image.Image:
    target = Image.new("P", source.size, 0)
    target.paste(source, (x_offset, y_offset))
    return target


def animate_jelly(base: Image.Image) -> list[Image.Image]:
    bbox = base.getbbox()
    if not bbox:
        raise ValueError("blank jelly anchor")
    left, top, right, bottom = bbox
    source = base.crop(bbox)
    squeezes = [0, 2, 3, 1]
    sways = [0, 2, 0, -2]
    frames = []
    for squeeze, sway in zip(squeezes, sways):
        scaled = source.resize((source.width, max(1, source.height - squeeze)), Image.Resampling.NEAREST)
        staged = Image.new("P", base.size, 0)
        base_x = left
        base_y = top + squeeze // 2
        split = max(1, int(scaled.height * 0.43))
        for row in range(scaled.height):
            ratio = max(0.0, (row - split) / max(1, scaled.height - split - 1))
            row_shift = round(sway * ratio)
            strip = scaled.crop((0, row, scaled.width, row + 1))
            staged.paste(strip, (base_x + row_shift, base_y + row))
        frames.append(staged)
    return frames


def animate_shark(base: Image.Image) -> list[Image.Image]:
    bbox = base.getbbox()
    if not bbox:
        raise ValueError("blank shark anchor")
    left, top, right, bottom = bbox
    tail_end = left + max(1, round((right - left) * 0.34))
    bends = [0, 2, 0, -2]
    bobs = [0, -1, 0, 1]
    frames = []
    for bend, bob in zip(bends, bobs):
        staged = Image.new("P", base.size, 0)
        for x in range(base.width):
            column = base.crop((x, 0, x + 1, base.height))
            if left <= x < tail_end:
                strength = (tail_end - x) / max(1, tail_end - left)
                y_shift = round(bend * strength)
            else:
                y_shift = 0
            staged.paste(column, (x, bob + y_shift))
        frames.append(staged)
    return frames


def connected_components(indexed: Image.Image) -> list[int]:
    width, height = indexed.size
    pixels = list(indexed.get_flattened_data())
    seen = bytearray(width * height)
    sizes = []
    for start, value in enumerate(pixels):
        if value == 0 or seen[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        size = 0
        while queue:
            position = queue.popleft()
            size += 1
            x, y = position % width, position // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    neighbor = ny * width + nx
                    if pixels[neighbor] != 0 and not seen[neighbor]:
                        seen[neighbor] = 1
                        queue.append(neighbor)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def pack_4bit(indexed: Image.Image) -> bytes:
    pixels = list(indexed.get_flattened_data())
    if len(pixels) % 2:
        pixels.append(0)
    return bytes((pixels[index] << 4) | pixels[index + 1] for index in range(0, len(pixels), 2))


def unpack_4bit(data: bytes, size: tuple[int, int]) -> list[int]:
    result = []
    for value in data:
        result.extend((value >> 4, value & 0x0F))
    return result[: size[0] * size[1]]


def rgb565(color: tuple[int, int, int, int]) -> int:
    red, green, blue, _ = color
    return ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)


def cpp_identifier(asset_id: str) -> str:
    return "".join(part.capitalize() for part in asset_id.split("_"))


def format_bytes(data: bytes, indent: str = "  ") -> str:
    rows = []
    for start in range(0, len(data), 16):
        rows.append(indent + ", ".join(f"0x{value:02X}" for value in data[start:start + 16]) + ",")
    return "\n".join(rows)


def build_header(assets: list[dict], palette: list[tuple[int, int, int, int]], packed_frames: dict[str, list[bytes]]) -> str:
    lines = [
        "#pragma once",
        "// Generated by scripts/build_creature_pack.py. Do not hand-edit.",
        "#include <Arduino.h>",
        "#include <pgmspace.h>",
        "",
        "namespace ocean_creatures {",
        "",
        "constexpr uint8_t kFrameCount = 4;",
        "const uint16_t kPalette565[16] PROGMEM = {",
        "  " + ", ".join(f"0x{rgb565(color):04X}" for color in palette) + ",",
        "};",
        "",
        "struct CreatureSprite {",
        "  const char* id;",
        "  uint16_t width;",
        "  uint16_t height;",
        "  uint8_t renderScale;",
        "  const uint8_t* const* frames;",
        "};",
        "",
    ]
    for asset in assets:
        identifier = cpp_identifier(asset["id"])
        for frame_index, frame in enumerate(packed_frames[asset["id"]]):
            lines.extend([
                f"const uint8_t k{identifier}Frame{frame_index}[] PROGMEM = {{",
                format_bytes(frame),
                "};",
            ])
        pointers = ", ".join(f"k{identifier}Frame{index}" for index in range(4))
        lines.extend([
            f"const uint8_t* const k{identifier}Frames[kFrameCount] PROGMEM = {{{pointers}}};",
            f"const CreatureSprite k{identifier} = {{\"{asset['id']}\", {asset['target_size'][0]}, {asset['target_size'][1]}, {asset['render_scale']}, k{identifier}Frames}};",
            "",
        ])
    lines.extend([
        "inline void drawIndexedFrame(uint16_t* framebuffer, int16_t stride, int16_t framebufferHeight,",
        "                             const CreatureSprite& sprite, uint8_t frameIndex,",
        "                             int16_t destinationX, int16_t destinationY, bool mirrorX = false) {",
        "  frameIndex %= kFrameCount;",
        "  const uint8_t* data = reinterpret_cast<const uint8_t*>(pgm_read_ptr(&sprite.frames[frameIndex]));",
        "  for (uint16_t sourceY = 0; sourceY < sprite.height; ++sourceY) {",
        "    for (uint16_t sourceX = 0; sourceX < sprite.width; ++sourceX) {",
        "      const uint32_t pixelIndex = static_cast<uint32_t>(sourceY) * sprite.width + sourceX;",
        "      const uint8_t packed = pgm_read_byte(data + pixelIndex / 2);",
        "      const uint8_t paletteIndex = (pixelIndex & 1) ? (packed & 0x0F) : (packed >> 4);",
        "      if (paletteIndex == 0) continue;",
        "      const uint16_t logicalX = mirrorX ? sprite.width - 1 - sourceX : sourceX;",
        "      const int16_t targetX = destinationX + logicalX * sprite.renderScale;",
        "      const int16_t targetY = destinationY + sourceY * sprite.renderScale;",
        "      const uint16_t color = pgm_read_word(&kPalette565[paletteIndex]);",
        "      for (uint8_t scaleY = 0; scaleY < sprite.renderScale; ++scaleY) {",
        "        const int16_t pixelY = targetY + scaleY;",
        "        if (pixelY < 0 || pixelY >= framebufferHeight) continue;",
        "        for (uint8_t scaleX = 0; scaleX < sprite.renderScale; ++scaleX) {",
        "          const int16_t pixelX = targetX + scaleX;",
        "          if (pixelX < 0 || pixelX >= stride) continue;",
        "          framebuffer[static_cast<uint32_t>(pixelY) * stride + pixelX] = color;",
        "        }",
        "      }",
        "    }",
        "  }",
        "}",
        "",
        "}  // namespace ocean_creatures",
        "",
    ])
    return "\n".join(lines)


def make_sprite_sheet(asset: dict, frames: list[Image.Image], palette: list[tuple[int, int, int, int]], destination: Path) -> None:
    scale = 4
    margin = 12
    label_height = 24
    width, height = asset["target_size"]
    canvas = Image.new("RGB", (margin * 2 + len(frames) * width * scale, margin * 2 + height * scale + label_height), "#071522")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=13)
    for index, frame in enumerate(frames):
        x = margin + index * width * scale
        checker = Image.new("RGBA", (width * scale, height * scale), "#0B2A3C")
        checker_draw = ImageDraw.Draw(checker)
        for yy in range(0, checker.height, 16):
            for xx in range(0, checker.width, 16):
                if (xx // 16 + yy // 16) % 2:
                    checker_draw.rectangle((xx, yy, xx + 15, yy + 15), fill="#124A60")
        rgba = indexed_to_rgba(frame, palette).resize(checker.size, Image.Resampling.NEAREST)
        checker.alpha_composite(rgba)
        canvas.paste(checker.convert("RGB"), (x, margin))
        draw.text((x + 4, margin + height * scale + 6), f"frame {index}", fill="#D8EEF0", font=font)
    canvas.save(destination, optimize=True)


def draw_ocean_background(frame: Image.Image) -> None:
    draw = ImageDraw.Draw(frame)
    for y in range(frame.height):
        mix = y / max(1, frame.height - 1)
        red = round(5 + 2 * mix)
        green = round(39 - 20 * mix)
        blue = round(58 - 24 * mix)
        draw.line((0, y, frame.width, y), fill=(red, green, blue, 255))
    draw.polygon([(0, 406), (72, 390), (145, 416), (230, 394), (frame.width, 410), (frame.width, frame.height), (0, frame.height)], fill=(7, 21, 34, 255))
    for x, y, radius in ((36, 112, 3), (49, 88, 2), (319, 182, 3), (330, 151, 2), (286, 274, 2)):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=(39, 211, 208, 255), width=1)


def make_device_previews(assets: list[dict], frames_by_asset: dict[str, list[Image.Image]], palette: list[tuple[int, int, int, int]]) -> None:
    gif_frames = []
    for tick in range(32):
        canvas = Image.new("RGBA", (368, 448), (0, 0, 0, 255))
        draw_ocean_background(canvas)
        frame_index = (tick // 2) % 4
        asset = assets[0] if tick < 16 else assets[1]
        sprite = indexed_to_rgba(frames_by_asset[asset["id"]][frame_index], palette)
        scale = asset["render_scale"]
        sprite = sprite.resize((sprite.width * scale, sprite.height * scale), Image.Resampling.NEAREST)
        x = (canvas.width - sprite.width) // 2
        y = (canvas.height - sprite.height) // 2 + round(math.sin(tick * math.pi / 8) * 5)
        canvas.alpha_composite(sprite, (x, y))
        gif_frames.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=64))
    gif_path = PRODUCTION_ROOT / "device_preview.gif"
    gif_frames[0].save(gif_path, save_all=True, append_images=gif_frames[1:], duration=100, loop=0, disposal=2)
    gif_frames[4].convert("RGB").save(PRODUCTION_ROOT / "device_preview.png", optimize=True)
    gif_frames[20].convert("RGB").save(PRODUCTION_ROOT / "device_preview_shark.png", optimize=True)


def build() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    selection = json.loads(SELECTION_PATH.read_text(encoding="utf-8"))["selections"]
    palette = rgba_palette(manifest)
    PRODUCTION_ROOT.mkdir(parents=True, exist_ok=True)
    assets = manifest["assets"]
    frames_by_asset: dict[str, list[Image.Image]] = {}
    packed_by_asset: dict[str, list[bytes]] = {}
    asset_reports = []

    for asset in assets:
        choice = selection[asset["id"]]
        source_path = CANDIDATE_ROOT / choice["vendor"] / f"{asset['id']}__{choice['seed']}.png"
        source_metadata_path = source_path.with_suffix(".json")
        if not source_path.exists():
            raise FileNotFoundError(f"selected candidate is missing: {source_path}")
        if not source_metadata_path.exists():
            raise FileNotFoundError(f"selected candidate metadata is missing: {source_metadata_path}")
        source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
        metadata_matches_selection = (
            source_metadata.get("vendor") == choice["vendor"]
            and source_metadata.get("asset_id") == asset["id"]
            and source_metadata.get("seed") == choice["seed"]
            and bool(source_metadata.get("prompt"))
        )
        with Image.open(source_path) as source:
            source.load()
            source_size = source.size
            anchor = normalize_candidate(source, asset, palette)
        if asset["animation"] == "jelly_pulse":
            frames = animate_jelly(anchor)
        elif asset["animation"] == "shark_swim":
            frames = animate_shark(anchor)
        else:
            raise ValueError(f"unsupported animation {asset['animation']}")
        packed_frames = [pack_4bit(frame) for frame in frames]
        decoded_ok = all(unpack_4bit(packed, frame.size) == list(frame.get_flattened_data()) for packed, frame in zip(packed_frames, frames))
        component_sizes = [connected_components(frame) for frame in frames]
        opaque_counts = [sum(1 for value in frame.get_flattened_data() if value) for frame in frames]
        edge_margins = []
        for frame in frames:
            bbox = frame.getbbox()
            if not bbox:
                edge_margins.append(0)
            else:
                edge_margins.append(min(bbox[0], bbox[1], frame.width - bbox[2], frame.height - bbox[3]))
        largest_component_ratios = [
            (sizes[0] / count if sizes and count else 0.0)
            for sizes, count in zip(component_sizes, opaque_counts)
        ]
        checks = {
            "source_is_128_square": source_size == (128, 128),
            "candidate_metadata_matches_selection": metadata_matches_selection,
            "four_frames": len(frames) == manifest["frame_count"],
            "target_dimensions": all(list(frame.size) == asset["target_size"] for frame in frames),
            "nonempty_frames": all(count > 0 for count in opaque_counts),
            "four_bit_roundtrip": decoded_ok,
            "canvas_safety": min(edge_margins) >= 2,
            "coherent_subject": min(largest_component_ratios) >= 0.90,
            "bounded_palette": all(max(frame.get_flattened_data()) <= 15 for frame in frames),
        }
        if not all(checks.values()):
            failed = ", ".join(name for name, passed in checks.items() if not passed)
            raise RuntimeError(f"{asset['id']} failed production gates: {failed}")

        anchor_path = PRODUCTION_ROOT / f"{asset['id']}.png"
        indexed_to_rgba(frames[0], palette).save(anchor_path, optimize=True)
        sheet_path = PRODUCTION_ROOT / f"{asset['id']}_sheet.png"
        make_sprite_sheet(asset, frames, palette, sheet_path)
        frames_by_asset[asset["id"]] = frames
        packed_by_asset[asset["id"]] = packed_frames
        asset_reports.append({
            "id": asset["id"],
            "selection": choice,
            "source": str(source_path.relative_to(ROOT)),
            "source_sha256": sha256_file(source_path),
            "source_metadata": str(source_metadata_path.relative_to(ROOT)),
            "source_metadata_sha256": sha256_file(source_metadata_path),
            "source_prompt_sha256": sha256_bytes(source_metadata["prompt"].encode("utf-8")),
            "runtime_png": str(anchor_path.relative_to(ROOT)),
            "runtime_png_sha256": sha256_file(anchor_path),
            "sheet": str(sheet_path.relative_to(ROOT)),
            "sheet_sha256": sha256_file(sheet_path),
            "target_size": asset["target_size"],
            "render_scale": asset["render_scale"],
            "display_size": [value * asset["render_scale"] for value in asset["target_size"]],
            "packed_bytes_per_frame": len(packed_frames[0]),
            "packed_sha256": [sha256_bytes(frame) for frame in packed_frames],
            "opaque_pixels": opaque_counts,
            "component_sizes": component_sizes,
            "edge_margins": edge_margins,
            "checks": checks,
        })

    HEADER_PATH.write_text(build_header(assets, palette, packed_by_asset), encoding="utf-8")
    make_device_previews(assets, frames_by_asset, palette)
    report = {
        "schema_version": 1,
        "status": "passed",
        "builder": str(BUILDER_PATH.relative_to(ROOT)),
        "builder_sha256": sha256_file(BUILDER_PATH),
        "source_manifest_sha256": sha256_file(MANIFEST_PATH),
        "selection_sha256": sha256_file(SELECTION_PATH),
        "header": str(HEADER_PATH.relative_to(ROOT)),
        "header_sha256": sha256_file(HEADER_PATH),
        "device_preview": "creatures/generated/production/device_preview.png",
        "device_preview_sha256": sha256_file(PRODUCTION_ROOT / "device_preview.png"),
        "device_preview_shark": "creatures/generated/production/device_preview_shark.png",
        "device_preview_shark_sha256": sha256_file(PRODUCTION_ROOT / "device_preview_shark.png"),
        "device_animation": "creatures/generated/production/device_preview.gif",
        "device_animation_sha256": sha256_file(PRODUCTION_ROOT / "device_preview.gif"),
        "total_packed_frame_bytes": sum(len(frame) for frames in packed_by_asset.values() for frame in frames),
        "assets": asset_reports,
    }
    PRODUCTION_MANIFEST_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def check() -> None:
    report = json.loads(PRODUCTION_MANIFEST_PATH.read_text(encoding="utf-8"))
    if report.get("status") != "passed":
        raise SystemExit("creature production manifest is not passed")
    if report.get("builder") != str(BUILDER_PATH.relative_to(ROOT)) or \
            sha256_file(BUILDER_PATH) != report.get("builder_sha256"):
        raise SystemExit("creature pack builder changed; rebuild the pack")
    paths = [(ROOT / report["header"], report["header_sha256"]),
             (ROOT / report["device_preview"], report["device_preview_sha256"]),
             (ROOT / report["device_preview_shark"], report["device_preview_shark_sha256"]),
             (ROOT / report["device_animation"], report["device_animation_sha256"])]
    for asset in report["assets"]:
        paths.extend([
            (ROOT / asset["source"], asset["source_sha256"]),
            (ROOT / asset["source_metadata"], asset["source_metadata_sha256"]),
            (ROOT / asset["runtime_png"], asset["runtime_png_sha256"]),
            (ROOT / asset["sheet"], asset["sheet_sha256"]),
        ])
        if not all(asset["checks"].values()):
            raise SystemExit(f"stored audit is not passing for {asset['id']}")
    for path, expected_hash in paths:
        if not path.exists() or sha256_file(path) != expected_hash:
            raise SystemExit(f"creature artifact hash mismatch: {path}")
    if sha256_file(MANIFEST_PATH) != report["source_manifest_sha256"]:
        raise SystemExit("creature source manifest changed; rebuild the pack")
    if sha256_file(SELECTION_PATH) != report["selection_sha256"]:
        raise SystemExit("creature selection changed; rebuild the pack")
    print(f"Creature pack verified: {len(report['assets'])} assets, {report['total_packed_frame_bytes']} packed bytes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify checked-in production artifacts without rebuilding")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        report = build()
        print(f"Built {len(report['assets'])} creatures into {report['total_packed_frame_bytes']} bytes")
        print(HEADER_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
