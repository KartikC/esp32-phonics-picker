#!/usr/bin/env python3
"""Build semantic Evolutionary 16-bit creatures and fail-closed anatomy masks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = Path(__file__).resolve()
MANIFEST_PATH = ROOT / "creatures" / "variation" / "variation_manifest.json"
OUTPUT_ROOT = ROOT / "creatures" / "variation" / "generated"
REPORT_PATH = OUTPUT_ROOT / "variation_report.json"
HEADER_PATH = ROOT / "firmware" / "CreatureAssets" / "GeneratedCreatureVariations.h"
BODY_ROLES = frozenset({2, 3, 4, 5, 6})
PATTERN_NAMES = ("solid", "spots", "stripes", "mottle")
MIN_RARE_VISIBLE_PIXELS = 24
MIN_RARE_RETENTION_PERCENT = 90
MIN_RARE_PRIMITIVE_VISIBLE_PIXELS = 8


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_color(value: str) -> tuple[int, int, int, int]:
    if len(value) == 9:
        return ImageColor.getcolor(value, "RGBA")
    red, green, blue = ImageColor.getrgb(value)
    return red, green, blue, 255


def luminance(color: tuple[int, int, int, int]) -> float:
    return 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]


def rgb565(color: tuple[int, int, int, int]) -> int:
    red, green, blue, _ = color
    return ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)


def normalize_source(source: Image.Image, asset: dict) -> Image.Image:
    rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
    rgba.putalpha(alpha)
    registration = asset.get("registration")
    if registration:
        source_left, source_top, source_right, source_bottom = (
            registration["source_anchor_box"]
        )
        target_left, target_top, target_right, target_bottom = (
            registration["target_anchor_box"]
        )
        if source_right <= source_left or source_bottom <= source_top:
            raise ValueError(f"{asset['id']} registration source box is empty")
        if target_right <= target_left or target_bottom <= target_top:
            raise ValueError(f"{asset['id']} registration target box is empty")
        scale_x = (source_right - source_left) / (target_right - target_left)
        scale_y = (source_bottom - source_top) / (target_bottom - target_top)
        width, height = asset["logical_size"]
        return rgba.transform(
            (width, height),
            Image.Transform.AFFINE,
            (
                scale_x,
                0.0,
                source_left - target_left * scale_x,
                0.0,
                scale_y,
                source_top - target_top * scale_y,
            ),
            resample=Image.Resampling.NEAREST,
            fillcolor=(0, 0, 0, 0),
        )
    bbox = alpha.getbbox()
    if not bbox:
        raise ValueError(f"{asset['id']} source is blank")
    cropped = rgba.crop(bbox)
    content_width, content_height = asset["content_box"]
    scale = min(content_width / cropped.width, content_height / cropped.height)
    resized = cropped.resize(
        (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))),
        Image.Resampling.NEAREST,
    )
    width, height = asset["logical_size"]
    placed = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    placed.alpha_composite(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    return placed


def semantic_image(rgba: Image.Image, color_roles: dict[str, int], asset_id: str) -> Image.Image:
    semantic = Image.new("P", rgba.size, 0)
    output: list[int] = []
    unknown: set[str] = set()
    for red, green, blue, alpha in rgba.get_flattened_data():
        if alpha < 128:
            output.append(0)
            continue
        key = f"#{red:02X}{green:02X}{blue:02X}"
        role = color_roles.get(key)
        if role is None:
            unknown.add(key)
            output.append(0)
        else:
            output.append(role)
    if unknown:
        raise ValueError(f"{asset_id} contains unmapped colors: {', '.join(sorted(unknown))}")
    semantic.putdata(output)
    return semantic


def load_authored_animation(
    asset: dict,
    color_roles: dict[str, int],
) -> tuple[list[Image.Image], dict] | None:
    definition = asset.get("authored_animation")
    if not definition:
        return None
    manifest_path = ROOT / definition["manifest"]
    report_path = ROOT / definition["report"]
    animation_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "reviewed_for_device_test":
        raise RuntimeError(
            f"{asset['id']} authored animation is not approved for device test"
        )
    checks = report.get("checks")
    if not isinstance(checks, dict) or not checks or not all(checks.values()):
        raise RuntimeError(f"{asset['id']} authored animation review gates failed")
    if report.get("manifest") != definition["manifest"]:
        raise RuntimeError(f"{asset['id']} authored animation manifest path drifted")
    if report.get("manifest_sha256") != sha256_file(manifest_path):
        raise RuntimeError(f"{asset['id']} authored animation manifest hash drifted")
    if animation_manifest.get("visual_approval", {}).get("status") != \
            "approved_for_device_test":
        raise RuntimeError(f"{asset['id']} authored animation approval was revoked")
    records = report.get("frames")
    if not isinstance(records, list) or len(records) != 4:
        raise RuntimeError(f"{asset['id']} authored animation needs four frames")
    semantic_frames = []
    for expected_index, record in enumerate(records):
        if record.get("index") != expected_index:
            raise RuntimeError(f"{asset['id']} authored frame order drifted")
        path = ROOT / record["path"]
        if sha256_file(path) != record.get("sha256"):
            raise RuntimeError(f"{asset['id']} authored frame {expected_index} hash drifted")
        with Image.open(path) as image:
            image.load()
            normalized = normalize_source(image, asset)
        semantic_frames.append(apply_semantic_overrides(
            semantic_image(normalized, color_roles, asset["id"]),
            asset.get("semantic_overrides", []),
        ))
    return semantic_frames, {
        "manifest": definition["manifest"],
        "manifest_sha256": sha256_file(manifest_path),
        "report": definition["report"],
        "report_sha256": sha256_file(report_path),
        "provider_balance_cost": report.get("provider_balance_cost"),
        "provider_model": report.get("provider_model"),
        "reviewed_spritesheet": report.get("reviewed_spritesheet"),
        "reviewed_spritesheet_sha256": report.get(
            "reviewed_spritesheet_sha256"
        ),
    }


def apply_authored_frame_delta(
    base: Image.Image,
    treated_base: Image.Image,
    authored_frame: Image.Image,
) -> Image.Image:
    output = Image.new("P", base.size, 0)
    output.putdata([
        frame_role if frame_role != base_role else treated_role
        for base_role, treated_role, frame_role in zip(
            base.get_flattened_data(),
            treated_base.get_flattened_data(),
            authored_frame.get_flattened_data(),
        )
    ])
    return output


def apply_semantic_overrides(semantic: Image.Image, overrides: list[dict]) -> Image.Image:
    output = semantic.copy()
    pixels = list(output.get_flattened_data())
    for override in overrides:
        region = draw_regions(
            [{"shape": override["shape"], "box": override["box"]}], output.size
        )
        region_pixels = list(region.get_flattened_data())
        source_roles = set(override["source_roles"])
        target_role = override["target_role"]
        pixels = [
            target_role if inside and role in source_roles else role
            for role, inside in zip(pixels, region_pixels)
        ]
    output.putdata(pixels)
    return output


def normalized_box(box: list[float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    return (
        round(box[0] * (width - 1)),
        round(box[1] * (height - 1)),
        round(box[2] * (width - 1)),
        round(box[3] * (height - 1)),
    )


def normalized_point(point: list[float], size: tuple[int, int]) -> tuple[int, int]:
    width, height = size
    return round(point[0] * (width - 1)), round(point[1] * (height - 1))


def draw_regions(regions: list[dict], size: tuple[int, int]) -> Image.Image:
    mask = Image.new("1", size, 0)
    draw = ImageDraw.Draw(mask)
    for region in regions:
        box = normalized_box(region["box"], size)
        if region["shape"] == "ellipse":
            draw.ellipse(box, fill=1)
        elif region["shape"] == "rectangle":
            draw.rectangle(box, fill=1)
        else:
            raise ValueError(f"unsupported mask primitive: {region['shape']}")
    return mask


def draw_rare_primitive(draw: ImageDraw.ImageDraw, primitive: dict,
                        size: tuple[int, int]) -> None:
    code = primitive["code"]
    shape = primitive["shape"]
    if code not in (1, 2, 3):
        raise ValueError(f"rare overlay code must be 1..3, got {code}")
    if shape in {"ellipse", "ellipse_outline"}:
        box = normalized_box(primitive["box"], size)
        if shape == "ellipse":
            draw.ellipse(box, fill=code)
        else:
            draw.ellipse(box, outline=code, width=primitive.get("width", 1))
    elif shape == "line":
        points = [normalized_point(point, size) for point in primitive["points"]]
        draw.line(points, fill=code, width=primitive.get("width", 1))
    elif shape == "polygon":
        points = [normalized_point(point, size) for point in primitive["points"]]
        draw.polygon(points, fill=code)
    else:
        raise ValueError(f"unsupported rare overlay primitive: {shape}")


def draw_rare_overlay(definition: dict, size: tuple[int, int]) -> Image.Image:
    overlay = Image.new("P", size, 0)
    draw = ImageDraw.Draw(overlay)
    for primitive in definition["overlay"]:
        draw_rare_primitive(draw, primitive, size)
    return overlay


def clip_rare_overlay(overlay: Image.Image, safe: Image.Image) -> Image.Image:
    clipped = overlay.copy()
    safe_pixels = [bool(value) for value in safe.get_flattened_data()]
    clipped.putdata([
        code if is_safe else 0
        for code, is_safe in zip(overlay.get_flattened_data(), safe_pixels)
    ])
    return clipped


def build_rare_overlay(definition: dict, safe: Image.Image) -> Image.Image:
    return clip_rare_overlay(draw_rare_overlay(definition, safe.size), safe)


def count_nonzero_pixels(image: Image.Image) -> int:
    return sum(bool(value) for value in image.get_flattened_data())


def connected_component_count(image: Image.Image) -> int:
    """Count 4-connected non-transparent components in a semantic frame."""
    width, height = image.size
    opaque = {index for index, value in enumerate(image.get_flattened_data()) if value}
    components = 0
    while opaque:
        components += 1
        pending = [opaque.pop()]
        while pending:
            index = pending.pop()
            x, y = index % width, index // width
            for neighbor_x, neighbor_y in (
                (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)
            ):
                if not (0 <= neighbor_x < width and 0 <= neighbor_y < height):
                    continue
                neighbor = neighbor_y * width + neighbor_x
                if neighbor in opaque:
                    opaque.remove(neighbor)
                    pending.append(neighbor)
    return components


def translated_role_pixels(image: Image.Image, role: int,
                           x_limit: int | None = None) -> set[tuple[int, int]]:
    width, _ = image.size
    return {
        (index % width, index // width)
        for index, value in enumerate(image.get_flattened_data())
        if value == role and (x_limit is None or index % width < x_limit)
    }


def rare_overlay_retention_report(definition: dict, safe: Image.Image) -> dict:
    authored = draw_rare_overlay(definition, safe.size)
    retained = clip_rare_overlay(authored, safe)
    authored_pixels = count_nonzero_pixels(authored)
    retained_pixels = count_nonzero_pixels(retained)
    primitives = []
    for index, primitive in enumerate(definition["overlay"]):
        primitive_image = Image.new("P", safe.size, 0)
        draw_rare_primitive(ImageDraw.Draw(primitive_image), primitive, safe.size)
        primitive_authored = count_nonzero_pixels(primitive_image)
        primitive_retained = count_nonzero_pixels(
            clip_rare_overlay(primitive_image, safe)
        )
        primitives.append({
            "index": index,
            "shape": primitive["shape"],
            "code": primitive["code"],
            "authored_pixels": primitive_authored,
            "retained_pixels": primitive_retained,
            "clipped_pixels": primitive_authored - primitive_retained,
            "retention_percent": round(
                100.0 * primitive_retained / primitive_authored, 1
            ) if primitive_authored else 0.0,
        })
    overall_gate = (
        authored_pixels > 0 and
        retained_pixels * 100 >= authored_pixels * MIN_RARE_RETENTION_PERCENT
    )
    primitive_gate = bool(primitives) and all(
        item["authored_pixels"] > 0 and
        item["retained_pixels"] >= MIN_RARE_PRIMITIVE_VISIBLE_PIXELS and
        item["retained_pixels"] * 100 >=
            item["authored_pixels"] * MIN_RARE_RETENTION_PERCENT
        for item in primitives
    )
    return {
        "authored_pixels": authored_pixels,
        "retained_pixels": retained_pixels,
        "clipped_pixels": authored_pixels - retained_pixels,
        "retention_percent": round(
            100.0 * retained_pixels / authored_pixels, 1
        ) if authored_pixels else 0.0,
        "minimum_retention_percent": MIN_RARE_RETENTION_PERCENT,
        "minimum_primitive_visible_pixels":
            MIN_RARE_PRIMITIVE_VISIBLE_PIXELS,
        "overall_retention_gate": overall_gate,
        "primitive_retention_gate": primitive_gate,
        "gate_passed": overall_gate and primitive_gate,
        "primitives": primitives,
    }


def erode_opaque(semantic: Image.Image, radius: int = 2) -> Image.Image:
    width, height = semantic.size
    source = [value != 0 for value in semantic.get_flattened_data()]
    result = Image.new("1", semantic.size, 0)
    output = []
    for y in range(height):
        for x in range(width):
            keep = source[y * width + x]
            if keep:
                for yy in range(max(0, y - radius), min(height, y + radius + 1)):
                    for xx in range(max(0, x - radius), min(width, x + radius + 1)):
                        if not source[yy * width + xx]:
                            keep = False
                            break
                    if not keep:
                        break
            output.append(1 if keep else 0)
    result.putdata(output)
    return result


def build_safe_mask(semantic: Image.Image, definition: dict) -> Image.Image:
    included = draw_regions(definition["include"], semantic.size)
    excluded = draw_regions(definition["exclude"], semantic.size)
    inset = erode_opaque(semantic)
    semantic_pixels = list(semantic.get_flattened_data())
    include_pixels = list(included.get_flattened_data())
    exclude_pixels = list(excluded.get_flattened_data())
    inset_pixels = list(inset.get_flattened_data())
    allowed_roles = set(definition.get("allowed_roles", BODY_ROLES))
    safe = Image.new("1", semantic.size, 0)
    safe.putdata([
        1 if include and not exclude and inside and role in allowed_roles else 0
        for role, include, exclude, inside in zip(
            semantic_pixels, include_pixels, exclude_pixels, inset_pixels
        )
    ])
    return safe


def build_pattern_anchors(semantic: Image.Image) -> Image.Image:
    width, _ = semantic.size
    anchors = Image.new("I", semantic.size, 0)
    anchors.putdata([
        ((position % width) << 7) | (position // width) if role else 0
        for position, role in enumerate(semantic.get_flattened_data())
    ])
    return anchors


def transform_frame(
    source: Image.Image,
    animation: str,
    frame_index: int,
    geometry_bbox: tuple[int, int, int, int] | None = None,
) -> Image.Image:
    bbox = geometry_bbox or source.getbbox()
    if not bbox:
        return source.copy()
    left, top, right, bottom = bbox
    output = Image.new(source.mode, source.size, 0)
    if animation == "jelly_pulse":
        squeeze = (0, 2, 3, 1)[frame_index]
        sway = (0, 2, 0, -2)[frame_index]
        cropped = source.crop(bbox)
        scaled = cropped.resize((cropped.width, max(1, cropped.height - squeeze)), Image.Resampling.NEAREST)
        split = max(1, round(scaled.height * 0.43))
        for row in range(scaled.height):
            ratio = max(0.0, (row - split) / max(1, scaled.height - split - 1))
            row_shift = round(sway * ratio)
            output.paste(scaled.crop((0, row, scaled.width, row + 1)), (left + row_shift, top + squeeze // 2 + row))
    elif animation == "reviewed_chomp":
        # The reviewed source sheet already contains the complete animation.
        # Pattern masks, rare overlays, and anchors stay registered to the
        # motionless body, so their transform is deliberately the identity.
        return source.copy()
    elif animation == "octopus_sway":
        sway = (0, 2, 0, -2)[frame_index]
        bob = (0, -1, 0, 1)[frame_index]
        split = top + round((bottom - top) * 0.38)
        for y in range(source.height):
            strength = max(0.0, (y - split) / max(1, bottom - split))
            output.paste(source.crop((0, y, source.width, y + 1)), (round(sway * strength), y + bob))
    elif animation == "seahorse_bob":
        sway = (0, 1, 0, -1)[frame_index]
        bob = (0, -1, 0, 1)[frame_index]
        split = top + round((bottom - top) * 0.55)
        for y in range(source.height):
            strength = max(0.0, (y - split) / max(1, bottom - split))
            output.paste(source.crop((0, y, source.width, y + 1)), (round(sway * strength), y + bob))
    elif animation == "glass_squid_pulse":
        # Contract only the upper mantle. The paired eyes and internal column
        # remain fixed, while the connected arm tips receive a separate sway.
        contraction = (0, 2, 3, 1)[frame_index]
        sway = (0, 1, 0, -1)[frame_index]
        mantle_end = top + round((bottom - top) * 0.49)
        arm_start = top + round((bottom - top) * 0.70)
        for y in range(source.height):
            if top <= y < mantle_end:
                cropped = source.crop((left, y, right, y + 1))
                scaled = cropped.resize(
                    (max(1, cropped.width - contraction), 1),
                    Image.Resampling.NEAREST,
                )
                output.paste(scaled, (left + contraction // 2, y))
            elif arm_start <= y < bottom:
                strength = (y - arm_start) / max(1, bottom - arm_start - 1)
                output.paste(
                    source.crop((0, y, source.width, y + 1)),
                    (round(sway * strength), y),
                )
            else:
                output.paste(source.crop((0, y, source.width, y + 1)),
                             (0, y))
    elif animation == "anglerfish_hover":
        # The heavy head remains calm while the tail supplies a slow paddle.
        bend = (0, 2, 0, -2)[frame_index]
        bob = (0, -1, 0, 1)[frame_index]
        tail_end = left + max(1, round((right - left) * 0.35))
        for x in range(source.width):
            strength = ((tail_end - x) / max(1, tail_end - left)
                        if left <= x < tail_end else 0.0)
            output.paste(
                source.crop((x, 0, x + 1, source.height)),
                (x, bob + round(bend * strength)),
            )
    elif animation == "sea_angel_wingbeat":
        # Outer columns move symmetrically while the central body only bobs.
        wing = (0, -2, 0, 2)[frame_index]
        bob = (0, -1, 0, 1)[frame_index]
        center = (left + right - 1) / 2.0
        half_width = max(1.0, (right - left) / 2.0)
        for x in range(source.width):
            strength = min(1.0, abs(x - center) / half_width)
            output.paste(
                source.crop((x, 0, x + 1, source.height)),
                (x, bob + round(wing * strength)),
            )
    elif animation == "eel_undulate":
        # One low-amplitude traveling bend moves down the long connected body.
        # It fades before the enlarged head so the eye, mouth, and pouch remain
        # calm instead of being sheared by the body wave.
        phase = frame_index * math.pi / 2.0
        span = max(1, right - left - 1)
        for x in range(source.width):
            position = (x - left) / span
            head_fade = max(0.0, min(1.0, (0.78 - position) / 0.18))
            shift = round(
                1.75 * head_fade * math.sin(position * math.tau + phase)
            )
            output.paste(
                source.crop((x, 0, x + 1, source.height)),
                (x, shift),
            )
    else:
        raise ValueError(f"unsupported animation: {animation}")
    return output


def transform_semantic_frame(
    source: Image.Image,
    animation: str,
    frame_index: int,
    geometry_bbox: tuple[int, int, int, int],
) -> Image.Image:
    return transform_frame(source, animation, frame_index, geometry_bbox)


def pack_4bit(image: Image.Image) -> bytes:
    pixels = list(image.get_flattened_data())
    if len(pixels) % 2:
        pixels.append(0)
    return bytes((pixels[index] << 4) | pixels[index + 1] for index in range(0, len(pixels), 2))


def unpack_4bit(data: bytes, pixel_count: int) -> list[int]:
    output: list[int] = []
    for value in data:
        output.extend((value >> 4, value & 0x0F))
    return output[:pixel_count]


def pack_1bit(mask: Image.Image) -> bytes:
    pixels = [1 if value else 0 for value in mask.get_flattened_data()]
    output = bytearray()
    for start in range(0, len(pixels), 8):
        byte = 0
        for offset, value in enumerate(pixels[start:start + 8]):
            byte |= value << (7 - offset)
        output.append(byte)
    return bytes(output)


def unpack_1bit(data: bytes, pixel_count: int) -> list[int]:
    return [((data[index // 8] >> (7 - index % 8)) & 1) for index in range(pixel_count)]


def pack_2bit(image: Image.Image) -> bytes:
    pixels = list(image.get_flattened_data())
    output = bytearray()
    for start in range(0, len(pixels), 4):
        byte = 0
        for offset, value in enumerate(pixels[start:start + 4]):
            if not 0 <= value <= 3:
                raise ValueError(f"two-bit overlay value out of range: {value}")
            byte |= value << (6 - offset * 2)
        output.append(byte)
    return bytes(output)


def unpack_2bit(data: bytes, pixel_count: int) -> list[int]:
    return [((data[index // 4] >> (6 - (index % 4) * 2)) & 0x03) for index in range(pixel_count)]


def pattern_hash(x: int, y: int, seed: int) -> int:
    value = (seed ^ (x * 0x045D9F3B) ^ (y * 0x27D4EB2D)) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return value & 0xFFFFFFFF


def procedural_role(role: int, is_safe: bool, pattern: int, seed: int, x: int, y: int) -> int:
    if not is_safe or pattern == 0:
        return role
    if pattern == 1:  # clustered spots
        cell_x, cell_y = x // 7, y // 7
        hashed = pattern_hash(cell_x, cell_y, seed)
        center_x = 2 + (hashed & 0x03)
        center_y = 2 + ((hashed >> 2) & 0x03)
        radius = 1 + ((hashed >> 4) & 0x01)
        dx, dy = x % 7 - center_x, y % 7 - center_y
        if dx * dx + dy * dy <= radius * radius:
            return 9 if ((hashed >> 5) & 1) else 10
    elif pattern == 2:  # broad diagonal bands
        phase = (x * 2 + y + seed % 13) % 13
        if phase < 2:
            return 9
        if phase == 3:
            return 10
    elif pattern == 3:  # coarse organic mottle
        bucket = pattern_hash(x // 3, y // 3, seed) & 0x0F
        if bucket <= 3:
            return 9
        if bucket >= 14:
            return 10
    else:
        raise ValueError(f"unsupported procedural pattern: {pattern}")
    return role


def treated_indices(
    semantic: Image.Image,
    safe: Image.Image,
    rare: Image.Image,
    anchors: Image.Image,
    pattern: int,
    seed: int,
    rare_enabled: bool,
) -> list[int]:
    output = []
    rare_roles = (0, 9, 10, 14)
    for role, is_safe, rare_code, anchor in zip(
        semantic.get_flattened_data(), safe.get_flattened_data(),
        rare.get_flattened_data(), anchors.get_flattened_data()
    ):
        x, y = anchor >> 7, anchor & 0x7F
        treated = procedural_role(role, bool(is_safe), pattern, seed, x, y)
        if rare_enabled and rare_code:
            treated = rare_roles[rare_code]
        output.append(treated)
    return output


def probe_indices(semantic: Image.Image, safe: Image.Image, frame_index: int) -> list[int]:
    width, _ = semantic.size
    output = list(semantic.get_flattened_data())
    for position, is_safe in enumerate(safe.get_flattened_data()):
        x, y = position % width, position // width
        if is_safe and ((x * 3 + y * 5 + frame_index * 7) & 0x0F) < 3:
            output[position] = 9
    return output


def rgba_from_indices(indices: list[int], size: tuple[int, int], palette: list[tuple[int, int, int, int]]) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.putdata([palette[index] for index in indices])
    return image


def animation_frame_rgba(asset: dict, semantic: Image.Image,
                         palette: list[tuple[int, int, int, int]],
                         frame_index: int) -> Image.Image:
    glow = asset.get("pulsing_glow")
    glow_role = int(glow["role"]) if glow else -1
    glow_colors = (
        parse_color(glow["dim"]),
        parse_color(glow["medium"]),
        parse_color(glow["bright"]),
        parse_color(glow["medium"]),
    ) if glow else None
    colors = []
    for role in semantic.get_flattened_data():
        color = palette[role]
        if role == glow_role and glow_colors:
            color = glow_colors[frame_index % 4]
        colors.append(color)
    image = Image.new("RGBA", semantic.size, (0, 0, 0, 0))
    image.putdata(colors)
    return image


def mask_diagnostic(semantic: Image.Image, safe: Image.Image) -> Image.Image:
    pixels = []
    for role, is_safe in zip(semantic.get_flattened_data(), safe.get_flattened_data()):
        if role == 0:
            pixels.append((0, 0, 0, 0))
        elif is_safe:
            pixels.append((54, 222, 125, 255))
        elif role in {1, 11, 12, 15}:
            pixels.append((255, 241, 185, 255))
        else:
            pixels.append((186, 73, 148, 255))
    image = Image.new("RGBA", semantic.size, (0, 0, 0, 0))
    image.putdata(pixels)
    return image


def paste_center(canvas: Image.Image, sprite: Image.Image, box: tuple[int, int, int, int], scale: int) -> None:
    sprite = sprite.resize((sprite.width * scale, sprite.height * scale), Image.Resampling.NEAREST)
    left, top, right, bottom = box
    canvas.alpha_composite(sprite, (left + (right - left - sprite.width) // 2, top + (bottom - top - sprite.height) // 2))


def automatic_preview_palette(asset: dict, row: int,
                              palettes: list[list[tuple[int, int, int, int]]]
                              ) -> list[tuple[int, int, int, int]]:
    allowed = asset.get("automatic_palette_indices", [0, 1, 2, 4, 5])
    return palettes[allowed[row % len(allowed)]]


def make_palette_comparison(manifest: dict, frames: dict[str, list[Image.Image]], palettes: list[list[tuple[int, int, int, int]]]) -> Path:
    cell_width, cell_height = 244, 270
    header_height = 42
    canvas = Image.new("RGBA", (cell_width * len(palettes), header_height + cell_height * len(manifest["animals"])), "#06131D")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=14)
    for column, definition in enumerate(manifest["palettes"]):
        draw.text((column * cell_width + 10, 13), definition["label"], fill="#E8EEF0", font=font)
    for row, asset in enumerate(manifest["animals"]):
        top = header_height + row * cell_height
        draw.text((8, top + 7), asset["label"], fill="#D8E6E7", font=font)
        indices = list(frames[asset["id"]][0].get_flattened_data())
        for column, palette in enumerate(palettes):
            sprite = rgba_from_indices(indices, frames[asset["id"]][0].size, palette)
            box = (column * cell_width, top + 28, (column + 1) * cell_width, top + cell_height)
            paste_center(canvas, sprite, box, 2)
    destination = OUTPUT_ROOT / "palette_comparison.png"
    canvas.convert("RGB").save(destination, optimize=True)
    return destination


def make_animation_comparison(
    manifest: dict,
    frames: dict[str, list[Image.Image]],
    palettes: list[list[tuple[int, int, int, int]]],
) -> Path:
    cell_width, cell_height = 380, 390
    header_height = 44
    canvas = Image.new(
        "RGBA",
        (cell_width * manifest["frame_count"],
         header_height + cell_height * len(manifest["animals"])),
        "#06131D",
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=14)
    for frame_index in range(manifest["frame_count"]):
        draw.text((frame_index * cell_width + 12, 14),
                  f"frame {frame_index}", fill="#E8EEF0", font=font)
    for row, asset in enumerate(manifest["animals"]):
        top = header_height + row * cell_height
        draw.text((8, top + 8), asset["label"], fill="#D8E6E7", font=font)
        palette = automatic_preview_palette(asset, row, palettes)
        for frame_index, semantic in enumerate(frames[asset["id"]]):
            sprite = animation_frame_rgba(asset, semantic, palette, frame_index)
            paste_center(
                canvas,
                sprite,
                (frame_index * cell_width, top + 30,
                 (frame_index + 1) * cell_width, top + cell_height),
                asset["render_scale"],
            )
    destination = OUTPUT_ROOT / "animation_comparison.png"
    canvas.convert("RGB").save(destination, optimize=True)
    return destination


def make_protection_proof(manifest: dict, frames: dict[str, list[Image.Image]], masks: dict[str, list[Image.Image]], palette: list[tuple[int, int, int, int]]) -> Path:
    cell_width, cell_height = 380, 390
    header_height = 44
    labels = ("baked semantics", "authored safe map", "test texture probe", "changed pixels")
    canvas = Image.new("RGBA", (cell_width * 4, header_height + cell_height * len(manifest["animals"])), "#06131D")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=14)
    for column, label in enumerate(labels):
        draw.text((column * cell_width + 12, 14), label, fill="#E8EEF0", font=font)
    for row, asset in enumerate(manifest["animals"]):
        semantic = frames[asset["id"]][0]
        safe = masks[asset["id"]][0]
        base = list(semantic.get_flattened_data())
        probe = probe_indices(semantic, safe, 0)
        changed = []
        safe_pixels = list(safe.get_flattened_data())
        for before, after, is_safe in zip(base, probe, safe_pixels):
            if before == 0:
                changed.append((0, 0, 0, 0))
            elif before != after and is_safe:
                changed.append((54, 222, 225, 255))
            elif before != after:
                changed.append((255, 45, 55, 255))
            else:
                changed.append((31, 43, 55, 255))
        changed_image = Image.new("RGBA", semantic.size, (0, 0, 0, 0))
        changed_image.putdata(changed)
        images = (
            rgba_from_indices(base, semantic.size, palette),
            mask_diagnostic(semantic, safe),
            rgba_from_indices(probe, semantic.size, palette),
            changed_image,
        )
        top = header_height + row * cell_height
        draw.text((8, top + 8), asset["label"], fill="#D8E6E7", font=font)
        for column, image in enumerate(images):
            paste_center(canvas, image, (column * cell_width, top + 30, (column + 1) * cell_width, top + cell_height), asset["render_scale"])
    destination = OUTPUT_ROOT / "protection_proof.png"
    canvas.convert("RGB").save(destination, optimize=True)
    return destination


def make_pattern_comparison(
    manifest: dict,
    frames: dict[str, list[Image.Image]],
    masks: dict[str, list[Image.Image]],
    rare_overlays: dict[str, list[Image.Image]],
    anchors: dict[str, list[Image.Image]],
    palettes: list[list[tuple[int, int, int, int]]],
) -> Path:
    cell_width, cell_height = 380, 390
    header_height = 44
    canvas = Image.new(
        "RGBA",
        (cell_width * len(PATTERN_NAMES), header_height + cell_height * len(manifest["animals"])),
        "#06131D",
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=14)
    for column, name in enumerate(PATTERN_NAMES):
        draw.text((column * cell_width + 12, 14), name, fill="#E8EEF0", font=font)
    for row, asset in enumerate(manifest["animals"]):
        semantic = frames[asset["id"]][0]
        safe = masks[asset["id"]][0]
        rare = rare_overlays[asset["id"]][0]
        anchor = anchors[asset["id"]][0]
        palette = automatic_preview_palette(asset, row, palettes)
        top = header_height + row * cell_height
        draw.text((8, top + 8), asset["label"], fill="#D8E6E7", font=font)
        for pattern in range(len(PATTERN_NAMES)):
            indices = treated_indices(semantic, safe, rare, anchor, pattern, 0x51A7 + row * 97, False)
            sprite = rgba_from_indices(indices, semantic.size, palette)
            column = pattern
            paste_center(
                canvas,
                sprite,
                (column * cell_width, top + 30, (column + 1) * cell_width, top + cell_height),
                asset["render_scale"],
            )
    destination = OUTPUT_ROOT / "stage3_pattern_comparison.png"
    canvas.convert("RGB").save(destination, optimize=True)
    return destination


def make_rare_comparison(
    manifest: dict,
    frames: dict[str, list[Image.Image]],
    masks: dict[str, list[Image.Image]],
    rare_overlays: dict[str, list[Image.Image]],
    anchors: dict[str, list[Image.Image]],
    palettes: list[list[tuple[int, int, int, int]]],
) -> Path:
    cell_width, cell_height = 360, 390
    header_height = 44
    labels = ("solid", "common texture", "rare authored treatment")
    canvas = Image.new("RGBA", (cell_width * 3, header_height + cell_height * len(manifest["animals"])), "#06131D")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=14)
    for column, label in enumerate(labels):
        draw.text((column * cell_width + 12, 14), label, fill="#E8EEF0", font=font)
    for row, asset in enumerate(manifest["animals"]):
        semantic = frames[asset["id"]][0]
        safe = masks[asset["id"]][0]
        rare = rare_overlays[asset["id"]][0]
        anchor = anchors[asset["id"]][0]
        palette = automatic_preview_palette(asset, row + 2, palettes)
        seed = 0xA11CE + row * 131
        treatments = (
            treated_indices(semantic, safe, rare, anchor, 0, seed, False),
            treated_indices(semantic, safe, rare, anchor, 2, seed, False),
            treated_indices(semantic, safe, rare, anchor, 0, seed, True),
        )
        top = header_height + row * cell_height
        draw.text(
            (8, top + 8),
            f"{asset['label']} - {asset['rare_treatment']['label']}",
            fill="#D8E6E7",
            font=font,
        )
        for column, indices in enumerate(treatments):
            sprite = rgba_from_indices(indices, semantic.size, palette)
            paste_center(
                canvas,
                sprite,
                (column * cell_width, top + 30, (column + 1) * cell_width, top + cell_height),
                asset["render_scale"],
            )
    destination = OUTPUT_ROOT / "stage4_rare_comparison.png"
    canvas.convert("RGB").save(destination, optimize=True)
    return destination


def format_bytes(data: bytes, indent: str = "  ") -> str:
    return "\n".join(
        indent + ", ".join(f"0x{value:02X}" for value in data[start:start + 16]) + ","
        for start in range(0, len(data), 16)
    )


def format_words(data: list[int], indent: str = "  ") -> str:
    return "\n".join(
        indent + ", ".join(f"0x{value:04X}" for value in data[start:start + 12]) + ","
        for start in range(0, len(data), 12)
    )


def cpp_identifier(asset_id: str) -> str:
    return "".join(part.capitalize() for part in asset_id.split("_"))


def cpp_base_rarity(value: str) -> str:
    mapping = {
        "basic": "CreatureBaseRarity::kBasic",
        "medium": "CreatureBaseRarity::kMedium",
        "rare": "CreatureBaseRarity::kRare",
    }
    try:
        return mapping[value]
    except KeyError as error:
        raise ValueError(f"unsupported creature base rarity: {value}") from error


def build_header(
    manifest: dict,
    palettes: list[list[tuple[int, int, int, int]]],
    packed_frames: dict[str, list[bytes]],
    packed_masks: dict[str, list[bytes]],
    packed_rare: dict[str, list[bytes]],
    packed_anchors: dict[str, list[list[int]]],
) -> str:
    lines = [
        "#pragma once",
        "// Generated by scripts/build_creature_variations.py. Do not hand-edit.",
        "#include <Arduino.h>",
        "#include <pgmspace.h>",
        "",
        "namespace creature_variations {",
        "",
        f"constexpr uint8_t kFrameCount = {manifest['frame_count']};",
        f"constexpr uint8_t kPaletteCount = {len(palettes)};",
        f"constexpr uint8_t kCreatureCount = {len(manifest['animals'])};",
        "enum class CreatureBaseRarity : uint8_t { kBasic = 0, kMedium = 1, kRare = 2 };",
        "enum class RenderMode : uint8_t { kColor = 0, kProtectionMask = 1, kTextureProbe = 2 };",
        "enum class PatternStyle : uint8_t { kSolid = 0, kSpots = 1, kStripes = 2, kMottle = 3 };",
        "constexpr uint8_t kPatternCount = 4;",
        "",
        "const uint16_t kPalettes565[kPaletteCount][16] PROGMEM = {",
    ]
    for palette in palettes:
        lines.append("  {" + ", ".join(f"0x{rgb565(color):04X}" for color in palette) + "},")
    lines.extend(["};", "", "const char* const kPaletteNames[kPaletteCount] = {"])
    lines.append("  " + ", ".join(f'"{definition["label"]}"' for definition in manifest["palettes"]) + ",")
    lines.extend([
        "};",
        "",
        "struct CreatureSprite {",
        "  const char* id;",
        "  const char* label;",
        "  uint16_t width;",
        "  uint16_t height;",
        "  uint8_t renderScale;",
        "  CreatureBaseRarity baseRarity;",
        "  uint8_t automaticPaletteMask;",
        "  bool celebrationSparkles;",
        "  int8_t pulsingGlowRole;",
        "  uint16_t glowDim565;",
        "  uint16_t glowMedium565;",
        "  uint16_t glowBright565;",
        "  const char* rareTreatmentLabel;",
        "  const uint8_t* const* semanticFrames;",
        "  const uint8_t* const* patternSafeFrames;",
        "  const uint8_t* const* rareOverlayFrames;",
        "  const uint16_t* const* patternAnchorFrames;",
        "};",
        "",
    ])
    for asset in manifest["animals"]:
        identifier = cpp_identifier(asset["id"])
        for index, data in enumerate(packed_frames[asset["id"]]):
            lines.extend([f"const uint8_t k{identifier}Semantic{index}[] PROGMEM = {{", format_bytes(data), "};"])
        for index, data in enumerate(packed_masks[asset["id"]]):
            lines.extend([f"const uint8_t k{identifier}Safe{index}[] PROGMEM = {{", format_bytes(data), "};"])
        for index, data in enumerate(packed_rare[asset["id"]]):
            lines.extend([f"const uint8_t k{identifier}Rare{index}[] PROGMEM = {{", format_bytes(data), "};"])
        for index, data in enumerate(packed_anchors[asset["id"]]):
            lines.extend([f"const uint16_t k{identifier}Anchor{index}[] PROGMEM = {{", format_words(data), "};"])
        semantic_pointers = ", ".join(f"k{identifier}Semantic{index}" for index in range(manifest["frame_count"]))
        mask_pointers = ", ".join(f"k{identifier}Safe{index}" for index in range(manifest["frame_count"]))
        rare_pointers = ", ".join(f"k{identifier}Rare{index}" for index in range(manifest["frame_count"]))
        anchor_pointers = ", ".join(f"k{identifier}Anchor{index}" for index in range(manifest["frame_count"]))
        width, height = asset["logical_size"]
        base_rarity = cpp_base_rarity(asset["base_rarity"])
        automatic_palettes = asset.get(
            "automatic_palette_indices", [0, 1, 2, 4, 5]
        )
        if (not automatic_palettes or len(set(automatic_palettes)) != len(automatic_palettes) or
                any(not 0 <= index < len(palettes) or index == 3
                    for index in automatic_palettes)):
            raise ValueError(
                f"{asset['id']} automatic palette list is empty, duplicated, out of range, or includes plum"
            )
        palette_mask = sum(1 << index for index in automatic_palettes)
        celebration_sparkles = "true" if asset.get(
            "celebration_sparkles", True
        ) else "false"
        glow = asset.get("pulsing_glow")
        glow_role = int(glow["role"]) if glow else -1
        if glow_role != -1 and not 1 <= glow_role <= 15:
            raise ValueError(
                f"{asset['id']} pulsing glow role must be -1 or 1..15"
            )
        glow_dim = rgb565(parse_color(glow["dim"])) if glow else 0
        glow_medium = rgb565(parse_color(glow["medium"])) if glow else 0
        glow_bright = rgb565(parse_color(glow["bright"])) if glow else 0
        lines.extend([
            f"const uint8_t* const k{identifier}Semantics[kFrameCount] PROGMEM = {{{semantic_pointers}}};",
            f"const uint8_t* const k{identifier}Masks[kFrameCount] PROGMEM = {{{mask_pointers}}};",
            f"const uint8_t* const k{identifier}RareFrames[kFrameCount] PROGMEM = {{{rare_pointers}}};",
            f"const uint16_t* const k{identifier}AnchorFrames[kFrameCount] PROGMEM = {{{anchor_pointers}}};",
            f'const CreatureSprite k{identifier} = {{"{asset["id"]}", "{asset["label"]}", {width}, {height}, {asset["render_scale"]}, {base_rarity}, 0x{palette_mask:02X}, {celebration_sparkles}, {glow_role}, 0x{glow_dim:04X}, 0x{glow_medium:04X}, 0x{glow_bright:04X}, "{asset["rare_treatment"]["label"]}", k{identifier}Semantics, k{identifier}Masks, k{identifier}RareFrames, k{identifier}AnchorFrames}};',
            "",
        ])
    creature_names = ", ".join(f"&k{cpp_identifier(asset['id'])}" for asset in manifest["animals"])
    for index, asset in enumerate(manifest["animals"]):
        lines.append(
            f"constexpr uint8_t k{cpp_identifier(asset['id'])}Index = {index};"
        )
    lines.append("")
    lines.extend([
        f"const CreatureSprite* const kCreatures[kCreatureCount] = {{{creature_names}}};",
        "",
        "inline uint8_t readSemantic(const uint8_t* data, uint32_t pixelIndex) {",
        "  const uint8_t packed = pgm_read_byte(data + pixelIndex / 2);",
        "  return (pixelIndex & 1) ? (packed & 0x0F) : (packed >> 4);",
        "}",
        "",
        "inline bool readPatternSafe(const uint8_t* data, uint32_t pixelIndex) {",
        "  return (pgm_read_byte(data + pixelIndex / 8) >> (7 - pixelIndex % 8)) & 1;",
        "}",
        "",
        "inline uint8_t readRareOverlay(const uint8_t* data, uint32_t pixelIndex) {",
        "  return (pgm_read_byte(data + pixelIndex / 4) >> (6 - (pixelIndex % 4) * 2)) & 0x03;",
        "}",
        "",
        "inline uint32_t patternHash(uint16_t x, uint16_t y, uint32_t seed) {",
        "  uint32_t value = seed ^ (static_cast<uint32_t>(x) * 0x045D9F3Bu) ^",
        "                   (static_cast<uint32_t>(y) * 0x27D4EB2Du);",
        "  value ^= value >> 16;",
        "  value *= 0x7FEB352Du;",
        "  value ^= value >> 15;",
        "  value *= 0x846CA68Bu;",
        "  value ^= value >> 16;",
        "  return value;",
        "}",
        "",
        "inline uint8_t applyProceduralPatternRole(uint8_t role, bool patternSafe,",
        "                                          PatternStyle pattern, uint32_t seed,",
        "                                          uint16_t sourceX, uint16_t sourceY) {",
        "  if (!patternSafe || pattern == PatternStyle::kSolid) return role;",
        "  if (pattern == PatternStyle::kSpots) {",
        "    const uint16_t cellX = sourceX / 7;",
        "    const uint16_t cellY = sourceY / 7;",
        "    const uint32_t hashed = patternHash(cellX, cellY, seed);",
        "    const int16_t dx = sourceX % 7 - (2 + (hashed & 0x03));",
        "    const int16_t dy = sourceY % 7 - (2 + ((hashed >> 2) & 0x03));",
        "    const int16_t radius = 1 + ((hashed >> 4) & 0x01);",
        "    if (dx * dx + dy * dy <= radius * radius) return ((hashed >> 5) & 1) ? 9 : 10;",
        "  } else if (pattern == PatternStyle::kStripes) {",
        "    const uint8_t phase = (sourceX * 2 + sourceY + seed % 13) % 13;",
        "    if (phase < 2) return 9;",
        "    if (phase == 3) return 10;",
        "  } else if (pattern == PatternStyle::kMottle) {",
        "    const uint8_t bucket = patternHash(sourceX / 3, sourceY / 3, seed) & 0x0F;",
        "    if (bucket <= 3) return 9;",
        "    if (bucket >= 14) return 10;",
        "  }",
        "  return role;",
        "}",
        "",
        "inline uint8_t applyCreatureTreatmentRole(uint8_t role, bool patternSafe,",
        "                                         uint8_t rareCode, PatternStyle pattern,",
        "                                         uint32_t seed, bool rareEnabled,",
        "                                         uint16_t sourceX, uint16_t sourceY) {",
        "  role = applyProceduralPatternRole(role, patternSafe, pattern, seed, sourceX, sourceY);",
        "  // A non-zero packed rare code is already clipped to the separately",
        "  // authored rare-safe geometry at build time. Common patterns still",
        "  // require patternSafe, but rare treatments do not share that mask.",
        "  if (rareEnabled && rareCode) {",
        "    constexpr uint8_t kRareRoles[4] = {0, 9, 10, 14};",
        "    role = kRareRoles[rareCode & 0x03];",
        "  }",
        "  return role;",
        "}",
        "",
        "inline uint8_t applyTextureProbeRole(uint8_t role, bool patternSafe,",
        "                                     uint16_t sourceX, uint16_t sourceY, uint8_t frameIndex) {",
        "  if (patternSafe && ((sourceX * 3 + sourceY * 5 + frameIndex * 7) & 0x0F) < 3) return 9;",
        "  return role;",
        "}",
        "",
        "inline uint16_t applyCreatureGlow(const CreatureSprite& sprite, uint8_t semanticRole,",
        "                                    uint8_t rareCode, uint8_t frameIndex, uint16_t color) {",
        "  if (sprite.pulsingGlowRole < 0 || rareCode != 0 ||",
        "      semanticRole != static_cast<uint8_t>(sprite.pulsingGlowRole)) return color;",
        "  if ((frameIndex & 0x03) == 0) return sprite.glowDim565;",
        "  if ((frameIndex & 0x03) == 2) return sprite.glowBright565;",
        "  return sprite.glowMedium565;",
        "}",
        "",
        "inline void drawSemanticFrame(uint16_t* framebuffer, int16_t stride, int16_t framebufferHeight,",
        "                              const CreatureSprite& sprite, uint8_t frameIndex, uint8_t paletteIndex,",
        "                              RenderMode mode, int16_t destinationX, int16_t destinationY,",
        "                              PatternStyle pattern = PatternStyle::kSolid, uint32_t patternSeed = 0,",
        "                              bool rareEnabled = false) {",
        "  frameIndex %= kFrameCount;",
        "  paletteIndex %= kPaletteCount;",
        "  const uint8_t* semantic = reinterpret_cast<const uint8_t*>(pgm_read_ptr(&sprite.semanticFrames[frameIndex]));",
        "  const uint8_t* safeMask = reinterpret_cast<const uint8_t*>(pgm_read_ptr(&sprite.patternSafeFrames[frameIndex]));",
        "  const uint8_t* rareOverlay = reinterpret_cast<const uint8_t*>(pgm_read_ptr(&sprite.rareOverlayFrames[frameIndex]));",
        "  const uint16_t* patternAnchors = reinterpret_cast<const uint16_t*>(pgm_read_ptr(&sprite.patternAnchorFrames[frameIndex]));",
        "  for (uint16_t sourceY = 0; sourceY < sprite.height; ++sourceY) {",
        "    for (uint16_t sourceX = 0; sourceX < sprite.width; ++sourceX) {",
        "      const uint32_t pixelIndex = static_cast<uint32_t>(sourceY) * sprite.width + sourceX;",
        "      uint8_t role = readSemantic(semantic, pixelIndex);",
        "      if (role == 0) continue;",
        "      const uint8_t semanticRole = role;",
        "      const bool patternSafe = readPatternSafe(safeMask, pixelIndex);",
        "      const uint8_t rareCode = readRareOverlay(rareOverlay, pixelIndex);",
        "      const uint16_t patternAnchor = pgm_read_word(&patternAnchors[pixelIndex]);",
        "      const uint16_t patternX = patternAnchor >> 7;",
        "      const uint16_t patternY = patternAnchor & 0x7F;",
        "      uint16_t color;",
        "      if (mode == RenderMode::kProtectionMask) {",
        "        if (patternSafe) color = 0x36EF;",
        "        else if (role == 1 || role == 11 || role == 12 || role == 15) color = 0xFF97;",
        "        else color = 0xBA52;",
        "      } else {",
        "        if (mode == RenderMode::kTextureProbe)",
        "          role = applyTextureProbeRole(role, patternSafe, sourceX, sourceY, frameIndex);",
        "        else role = applyCreatureTreatmentRole(role, patternSafe, rareCode, pattern,",
        "                                               patternSeed, rareEnabled, patternX, patternY);",
        "        color = pgm_read_word(&kPalettes565[paletteIndex][role]);",
        "        color = applyCreatureGlow(sprite, semanticRole, rareCode, frameIndex, color);",
        "      }",
        "      const int16_t targetX = destinationX + sourceX * sprite.renderScale;",
        "      const int16_t targetY = destinationY + sourceY * sprite.renderScale;",
        "      for (uint8_t yy = 0; yy < sprite.renderScale; ++yy) {",
        "        const int16_t pixelY = targetY + yy;",
        "        if (pixelY < 0 || pixelY >= framebufferHeight) continue;",
        "        for (uint8_t xx = 0; xx < sprite.renderScale; ++xx) {",
        "          const int16_t pixelX = targetX + xx;",
        "          if (pixelX >= 0 && pixelX < stride) framebuffer[static_cast<uint32_t>(pixelY) * stride + pixelX] = color;",
        "        }",
        "      }",
        "    }",
        "  }",
        "}",
        "",
        "}  // namespace creature_variations",
        "",
    ])
    return "\n".join(lines)


def build() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    if len(manifest["semantic_roles"]) != 16:
        raise ValueError("exactly 16 semantic roles are required for four-bit packing")
    color_roles = {key.upper(): value for key, value in manifest["source_color_roles"].items()}
    palettes = [[parse_color(value) for value in definition["colors"]] for definition in manifest["palettes"]]
    if len(palettes) != 6 or any(len(palette) != 16 for palette in palettes):
        raise ValueError("the comparison build requires six complete 16-role palettes")
    for definition, palette in zip(manifest["palettes"], palettes):
        ramp = [luminance(palette[index]) for index in (2, 3, 4, 5, 6)]
        if any(first >= second for first, second in zip(ramp, ramp[1:])):
            raise ValueError(f"{definition['id']} body ramp is not strictly increasing")

    frames: dict[str, list[Image.Image]] = {}
    masks: dict[str, list[Image.Image]] = {}
    rare_overlays: dict[str, list[Image.Image]] = {}
    anchors: dict[str, list[Image.Image]] = {}
    packed_frames: dict[str, list[bytes]] = {}
    packed_masks: dict[str, list[bytes]] = {}
    packed_rare: dict[str, list[bytes]] = {}
    packed_anchors: dict[str, list[list[int]]] = {}
    reports = []
    for asset in manifest["animals"]:
        asset_color_roles = dict(color_roles)
        asset_color_roles.update({
            key.upper(): value
            for key, value in asset.get("source_color_roles", {}).items()
        })
        source_path = ROOT / asset["source"]
        with Image.open(source_path) as source:
            source.load()
            source_size = source.size
            normalized = normalize_source(source, asset)
        base = apply_semantic_overrides(
            semantic_image(normalized, asset_color_roles, asset["id"]),
            asset.get("semantic_overrides", []),
        )
        safe = build_safe_mask(base, asset["pattern_safe"])
        rare_safe = build_safe_mask(
            base, asset.get("rare_safe", asset["pattern_safe"])
        )
        rare = build_rare_overlay(asset["rare_treatment"], rare_safe)
        rare_retention = rare_overlay_retention_report(
            asset["rare_treatment"], rare_safe
        )
        anchor = build_pattern_anchors(base)
        geometry_bbox = base.getbbox()
        if not geometry_bbox:
            raise ValueError(f"{asset['id']} semantic base is blank")
        authored = load_authored_animation(asset, asset_color_roles)
        authored_provenance = None
        if authored:
            asset_frames, authored_provenance = authored
            if list(asset_frames[0].get_flattened_data()) != \
                    list(base.get_flattened_data()):
                raise RuntimeError(
                    f"{asset['id']} authored frame zero is not the selected source"
                )
        else:
            asset_frames = [
                transform_semantic_frame(
                    base, asset["animation"], index, geometry_bbox
                )
                for index in range(manifest["frame_count"])
            ]
        asset_masks = [
            transform_frame(safe, asset["animation"], index, geometry_bbox).convert("1")
            for index in range(manifest["frame_count"])
        ]
        asset_rare_masks = [
            transform_frame(rare_safe, asset["animation"], index, geometry_bbox).convert("1")
            for index in range(manifest["frame_count"])
        ]
        asset_rare = [
            transform_frame(rare, asset["animation"], index, geometry_bbox).convert("P")
            for index in range(manifest["frame_count"])
        ]
        asset_anchors = [
            transform_frame(anchor, asset["animation"], index, geometry_bbox).convert("I")
            for index in range(manifest["frame_count"])
        ]
        asset_packed = [pack_4bit(frame) for frame in asset_frames]
        unique_frame_count = len(set(asset_packed))
        if unique_frame_count < 3:
            raise RuntimeError(
                f"{asset['id']} animation has only {unique_frame_count} unique frames"
            )
        connected_components = [
            connected_component_count(frame) for frame in asset_frames
        ]
        base_component_count = connected_component_count(base)
        new_species = {
            "glass_squid", "anglerfish", "sea_angel", "gulper_eel"
        }
        if (
            any(count > base_component_count for count in connected_components)
            or (
                asset["id"] in new_species
                and any(count != 1 for count in connected_components)
            )
        ):
            raise RuntimeError(
                f"{asset['id']} animation disconnected its silhouette: "
                f"base={base_component_count}, frames={connected_components}"
            )

        glow = asset.get("pulsing_glow")
        glow_luminances = None
        glow_frame_luminances = None
        if glow:
            glow_luminances = [
                luminance(parse_color(glow[key]))
                for key in ("dim", "medium", "bright")
            ]
            glow_frame_luminances = [
                glow_luminances[index] for index in (0, 1, 2, 1)
            ]
            if not glow_luminances[0] < glow_luminances[1] < glow_luminances[2]:
                raise RuntimeError(
                    f"{asset['id']} glow ramp is not dim < medium < bright"
                )
            glow_role = int(glow["role"])
            if any(glow_role not in frame.get_flattened_data() for frame in asset_frames):
                raise RuntimeError(
                    f"{asset['id']} glow role is missing from an animation frame"
                )

        animation_audit = {
            "silhouette_component_count_does_not_increase": all(
                count <= base_component_count for count in connected_components
            ),
            "new_species_is_single_connected_component": (
                asset["id"] not in new_species
                or all(count == 1 for count in connected_components)
            ),
        }
        authored_semantic_change_masks = [
            [False] * (base.width * base.height)
            for _ in range(manifest["frame_count"])
        ]
        if asset["id"] == "reef_shark":
            if authored_provenance is None:
                raise RuntimeError("reef_shark must use its reviewed sprite sheet")
            mouth_roi = (70, 102, base.width - 1, base.height - 1)
            eye_base = translated_role_pixels(base, 11)
            gill_base = translated_role_pixels(base, 12, 80)
            chomp_change_counts = []
            changes_bounded_to_mouth = []
            changes_avoid_treatment_masks = []
            opacity_within_five_percent = []
            mouth_dark_counts = []
            mouth_glint_counts = []
            for frame_index, frame in enumerate(asset_frames):
                frame_pixels = list(frame.get_flattened_data())
                base_pixels = list(base.get_flattened_data())
                changed = [
                    before != after
                    for before, after in zip(base_pixels, frame_pixels)
                ]
                changed_positions = [
                    (position % frame.width, position // frame.width)
                    for position, is_changed in enumerate(changed)
                    if is_changed
                ]
                roi_left, roi_top, roi_right, roi_bottom = mouth_roi
                changes_bounded_to_mouth.append(all(
                    roi_left <= x <= roi_right and
                    roi_top <= y <= roi_bottom
                    for x, y in changed_positions
                ))
                safe_pixels = list(
                    asset_masks[frame_index].get_flattened_data()
                )
                rare_safe_pixels = list(
                    asset_rare_masks[frame_index].get_flattened_data()
                )
                changes_avoid_treatment_masks.append(all(
                    not is_changed or (not is_safe and not is_rare_safe)
                    for is_changed, is_safe, is_rare_safe in zip(
                        changed, safe_pixels, rare_safe_pixels
                    )
                ))
                chomp_change_counts.append(sum(changed))
                roi_roles = [
                    frame.getpixel((x, y))
                    for y in range(roi_top, roi_bottom + 1)
                    for x in range(roi_left, roi_right + 1)
                ]
                mouth_dark_counts.append(sum(role in {1, 2} for role in roi_roles))
                mouth_glint_counts.append(sum(role == 15 for role in roi_roles))
                base_opacity = sum(role != 0 for role in base_pixels)
                frame_opacity = sum(role != 0 for role in frame_pixels)
                opacity_within_five_percent.append(
                    abs(frame_opacity - base_opacity) * 100 <= base_opacity * 5
                )
                authored_semantic_change_masks[frame_index] = [
                    before != after for before, after in zip(
                        base_pixels, frame_pixels
                    )
                ]
            animation_audit.update({
                "selected_82412_source_hash_is_fixed": (
                    sha256_file(source_path) ==
                    "0042e78252174923e339f3bf0f29d1b083bd26d9a0eddc0a4e80c91629e58c7c"
                ),
                "reviewed_provider_gates_passed": bool(authored_provenance),
                "fixed_banking_registration_is_120_by_124": (
                    base.size == (120, 124) and asset["render_scale"] == 3
                ),
                "seven_pixel_eye_is_fixed": (
                    len(eye_base) == 7 and all(
                        translated_role_pixels(frame, 11) == eye_base
                        for frame in asset_frames
                    )
                ),
                "gills_are_fixed": all(
                    translated_role_pixels(frame, 12, 80) == gill_base
                    for frame in asset_frames
                ),
                "authored_changes_bounded_to_mouth_roi":
                    all(changes_bounded_to_mouth),
                "authored_changes_avoid_pattern_and_rare_regions":
                    all(changes_avoid_treatment_masks),
                "toothless_mouth_adds_no_glint_pixels": all(
                    count <= mouth_glint_counts[0]
                    for count in mouth_glint_counts
                ),
                "half_frames_are_identical": (
                    list(asset_frames[1].get_flattened_data()) ==
                    list(asset_frames[3].get_flattened_data())
                ),
                "authored_chomp_opacity_within_five_percent":
                    all(opacity_within_five_percent),
                "authored_chomp_is_one_connected_silhouette":
                    all(count == 1 for count in connected_components),
                "authored_closed_half_open_half_schedule": (
                    chomp_change_counts[0] == 0 and
                    chomp_change_counts[1] > 0 and
                    chomp_change_counts[2] > chomp_change_counts[1] and
                    chomp_change_counts[3] == chomp_change_counts[1]
                ),
                "dark_cavity_grows_closed_half_open_half": (
                    mouth_dark_counts[1] > mouth_dark_counts[0] and
                    mouth_dark_counts[2] > mouth_dark_counts[1] and
                    mouth_dark_counts[3] == mouth_dark_counts[1]
                ),
            })
        if asset["id"] == "giant_octopus":
            eye_role_pixels = []
            eye_role_boxes = []
            for frame in asset_frames:
                pixels = translated_role_pixels(frame, 11)
                eye_role_pixels.append(len(pixels))
                eye_role_boxes.append((
                    min(x for x, _ in pixels),
                    min(y for _, y in pixels),
                    max(x for x, _ in pixels),
                    max(y for _, y in pixels),
                ) if pixels else None)
            former_eye_shadow = draw_regions(
                [{"shape": "ellipse", "box": [0.39, 0.38, 0.47, 0.44]}],
                base.size,
            )
            former_eye_shadow_pixels = [
                role
                for role, inside in zip(
                    base.get_flattened_data(),
                    former_eye_shadow.get_flattened_data(),
                )
                if inside and role != 0
            ]
            animation_audit.update({
                "authored_eye_is_exactly_seven_pixels":
                    eye_role_pixels == [7, 7, 7, 7],
                "authored_eye_stays_small_and_with_mantle": all(
                    box is not None and
                    box[0] >= 48 and box[2] <= 51 and
                    box[1] >= 40 and box[3] <= 43 and
                    box[2] - box[0] + 1 <= 4 and
                    box[3] - box[1] + 1 <= 2
                    for box in eye_role_boxes
                ),
                "former_eye_shadow_is_uniform_mantle_shadow": (
                    len(former_eye_shadow_pixels) == 56 and
                    set(former_eye_shadow_pixels) == {3}
                ),
            })
        if glow_luminances:
            animation_audit.update({
                "fixed_glow_luminance_order":
                    glow_luminances[0] < glow_luminances[1] < glow_luminances[2],
                "fixed_glow_frame_schedule":
                    glow_frame_luminances[0] < glow_frame_luminances[1] <
                    glow_frame_luminances[2] and
                    glow_frame_luminances[1] == glow_frame_luminances[3],
            })
        if not all(animation_audit.values()):
            raise RuntimeError(
                f"{asset['id']} failed animation audit: {animation_audit}"
            )
        mask_packed = [pack_1bit(mask) for mask in asset_masks]
        rare_packed = [pack_2bit(overlay) for overlay in asset_rare]
        anchor_packed = [list(frame.get_flattened_data()) for frame in asset_anchors]
        base_pixels_lookup = list(base.get_flattened_data())
        base_safe_lookup = [bool(value) for value in safe.get_flattened_data()]
        base_rare_safe_lookup = [
            bool(value) for value in rare_safe.get_flattened_data()
        ]
        base_rare_lookup = list(rare.get_flattened_data())
        audit_pattern_seed = 0xC0DEC0DE
        expected_pattern_frames: dict[str, list[Image.Image]] = {}
        for pattern_index, pattern_name in enumerate(PATTERN_NAMES[1:], start=1):
            treated_base = Image.new("P", base.size, 0)
            treated_base.putdata(treated_indices(
                base, safe, rare, anchor, pattern_index,
                audit_pattern_seed, False,
            ))
            if authored_provenance:
                expected_pattern_frames[pattern_name] = [
                    apply_authored_frame_delta(base, treated_base, frame)
                    for frame in asset_frames
                ]
            else:
                expected_pattern_frames[pattern_name] = [
                    transform_semantic_frame(
                        treated_base, asset["animation"], index, geometry_bbox
                    ).convert("P")
                    for index in range(manifest["frame_count"])
                ]
        rare_treated_base = Image.new("P", base.size, 0)
        rare_treated_base.putdata(treated_indices(
            base, safe, rare, anchor, 0, audit_pattern_seed, True,
        ))
        if authored_provenance:
            expected_rare_frames = [
                apply_authored_frame_delta(base, rare_treated_base, frame)
                for frame in asset_frames
            ]
        else:
            expected_rare_frames = [
                transform_semantic_frame(
                    rare_treated_base, asset["animation"], index, geometry_bbox
                ).convert("P")
                for index in range(manifest["frame_count"])
            ]
        protected_changes = []
        safe_changes = []
        frame_checks = []
        pattern_safe_changes: dict[str, list[int]] = {name: [] for name in PATTERN_NAMES[1:]}
        pattern_protected_changes: dict[str, list[int]] = {name: [] for name in PATTERN_NAMES[1:]}
        pattern_animation_mismatches: dict[str, list[int]] = {
            name: [] for name in PATTERN_NAMES[1:]
        }
        rare_authorized_changes = []
        rare_unauthorized_changes = []
        rare_animation_mismatches = []
        for frame_index, (semantic, pattern_safe, rare_authorized, rare_overlay, pattern_anchor, semantic_bytes, mask_bytes, rare_bytes) in enumerate(zip(
            asset_frames, asset_masks, asset_rare_masks, asset_rare, asset_anchors, asset_packed, mask_packed, rare_packed
        )):
            base_pixels = list(semantic.get_flattened_data())
            safe_pixels = [1 if value else 0 for value in pattern_safe.get_flattened_data()]
            anchor_pixels = list(pattern_anchor.get_flattened_data())
            probe = probe_indices(semantic, pattern_safe, frame_index)
            protected_change_count = sum(
                1 for before, after, is_safe in zip(base_pixels, probe, safe_pixels)
                if before != after and not is_safe
            )
            safe_change_count = sum(
                1 for before, after, is_safe in zip(base_pixels, probe, safe_pixels)
                if before != after and is_safe
            )
            protected_changes.append(protected_change_count)
            safe_changes.append(safe_change_count)
            rare_pixels = list(rare_overlay.get_flattened_data())
            rare_safe_pixels = [
                1 if value else 0
                for value in rare_authorized.get_flattened_data()
            ]
            for pattern_index, pattern_name in enumerate(PATTERN_NAMES[1:], start=1):
                treated = treated_indices(
                    semantic, pattern_safe, rare_overlay, pattern_anchor,
                    pattern_index, audit_pattern_seed, False,
                )
                pattern_safe_changes[pattern_name].append(sum(
                    1 for before, after, is_safe in zip(base_pixels, treated, safe_pixels)
                    if before != after and is_safe
                ))
                pattern_protected_changes[pattern_name].append(sum(
                    1 for before, after, is_safe in zip(base_pixels, treated, safe_pixels)
                    if before != after and not is_safe
                ))
                pattern_animation_mismatches[pattern_name].append(sum(
                    before != after for before, after in zip(
                        expected_pattern_frames[pattern_name][frame_index].get_flattened_data(),
                        treated,
                    )
                ))
            rare_treated = treated_indices(
                semantic, pattern_safe, rare_overlay, pattern_anchor,
                0, audit_pattern_seed, True,
            )
            rare_authorized_changes.append(sum(
                1 for before, after, is_rare_safe in zip(
                    base_pixels, rare_treated, rare_safe_pixels
                )
                if before != after and is_rare_safe
            ))
            rare_unauthorized_changes.append(sum(
                1 for before, after, is_rare_safe in zip(
                    base_pixels, rare_treated, rare_safe_pixels
                )
                if before != after and not is_rare_safe
            ))
            rare_animation_mismatches.append(sum(
                before != after for before, after in zip(
                    expected_rare_frames[frame_index].get_flattened_data(),
                    rare_treated,
                )
            ))
            frame_checks.append({
                "semantic_pack_roundtrip": unpack_4bit(semantic_bytes, len(base_pixels)) == base_pixels,
                "mask_pack_roundtrip": unpack_1bit(mask_bytes, len(base_pixels)) == safe_pixels,
                "rare_pack_roundtrip": unpack_2bit(rare_bytes, len(base_pixels)) == rare_pixels,
                "semantic_anchor_alignment": all(
                    role == 0 or (
                        (anchor >> 7) < base.width and
                        (anchor & 0x7F) < base.height and
                        base_pixels_lookup[
                            (anchor & 0x7F) * base.width + (anchor >> 7)
                        ] == role
                    ) or (
                        authored_semantic_change_masks[frame_index][position] and
                        not safe_pixels[position] and
                        not rare_safe_pixels[position] and
                        (
                            authored_provenance is not None or
                            role in {1, 7, 8, 12}
                        )
                    )
                    for position, (role, anchor) in enumerate(zip(
                        base_pixels, anchor_pixels
                    ))
                ),
                "safe_anchor_alignment": all(
                    not is_safe or base_safe_lookup[(anchor & 0x7F) * base.width + (anchor >> 7)]
                    for is_safe, anchor in zip(safe_pixels, anchor_pixels)
                ),
                "rare_safe_anchor_alignment": all(
                    not is_rare_safe or base_rare_safe_lookup[
                        (anchor & 0x7F) * base.width + (anchor >> 7)
                    ]
                    for is_rare_safe, anchor in zip(
                        rare_safe_pixels, anchor_pixels
                    )
                ),
                "rare_anchor_alignment": all(
                    code == 0 or base_rare_lookup[(anchor & 0x7F) * base.width + (anchor >> 7)] == code
                    for code, anchor in zip(rare_pixels, anchor_pixels)
                ),
                "safe_mask_subset_of_creature": all(not is_safe or role != 0 for role, is_safe in zip(base_pixels, safe_pixels)),
                "rare_overlay_subset_of_rare_safe_mask": all(
                    not code or is_rare_safe
                    for code, is_rare_safe in zip(
                        rare_pixels, rare_safe_pixels
                    )
                ),
                "protected_anatomy_unchanged": protected_change_count == 0,
                "probe_exercises_safe_region": safe_change_count > 0,
                "all_stage3_patterns_exercise_safe_region": all(
                    pattern_safe_changes[name][-1] > 0 for name in PATTERN_NAMES[1:]
                ),
                "all_stage3_patterns_preserve_protected_anatomy": all(
                    pattern_protected_changes[name][-1] == 0 for name in PATTERN_NAMES[1:]
                ),
                "all_stage3_patterns_follow_canonical_animation": all(
                    pattern_animation_mismatches[name][-1] == 0
                    for name in PATTERN_NAMES[1:]
                ),
                "stage4_rare_exercises_authored_region":
                    rare_authorized_changes[-1] >= MIN_RARE_VISIBLE_PIXELS,
                "stage4_rare_stays_inside_authored_region":
                    rare_unauthorized_changes[-1] == 0,
                "stage4_rare_follows_canonical_animation":
                    rare_animation_mismatches[-1] == 0,
                "stage4_authored_motif_retained":
                    rare_retention["gate_passed"],
            })
        if not all(all(check.values()) for check in frame_checks):
            failed = [
                f"frame {frame_index}: " + ", ".join(
                    name for name, passed in checks.items() if not passed
                )
                for frame_index, checks in enumerate(frame_checks)
                if not all(checks.values())
            ]
            raise RuntimeError(
                f"{asset['id']} failed semantic or protection gates: "
                + "; ".join(failed)
            )
        frames[asset["id"]] = asset_frames
        masks[asset["id"]] = asset_masks
        rare_overlays[asset["id"]] = asset_rare
        anchors[asset["id"]] = asset_anchors
        packed_frames[asset["id"]] = asset_packed
        packed_masks[asset["id"]] = mask_packed
        packed_rare[asset["id"]] = rare_packed
        packed_anchors[asset["id"]] = anchor_packed
        reports.append({
            "id": asset["id"],
            "source": asset["source"],
            "source_sha256": sha256_file(source_path),
            "source_size": list(source_size),
            "logical_size": asset["logical_size"],
            "display_size": [value * asset["render_scale"] for value in asset["logical_size"]],
            "base_rarity": asset["base_rarity"],
            "animation": asset["animation"],
            "authored_animation": authored_provenance,
            "unique_semantic_frame_count": unique_frame_count,
            "connected_component_count": connected_components,
            "animation_audit": animation_audit,
            "pulsing_glow": asset.get("pulsing_glow"),
            "glow_frame_luminances": glow_frame_luminances,
            "automatic_palette_indices": asset.get(
                "automatic_palette_indices", [0, 1, 2, 4, 5]
            ),
            "celebration_sparkles": asset.get(
                "celebration_sparkles", True
            ),
            "protected_anatomy": asset["pattern_safe"]["protected_anatomy"],
            "opaque_pixels": [sum(role != 0 for role in frame.get_flattened_data()) for frame in asset_frames],
            "pattern_safe_pixels": [sum(bool(value) for value in mask.get_flattened_data()) for mask in asset_masks],
            "rare_safe_pixels": [
                sum(bool(value) for value in mask.get_flattened_data())
                for mask in asset_rare_masks
            ],
            "protected_pixels": [sum(role != 0 and not bool(is_safe) for role, is_safe in zip(frame.get_flattened_data(), mask.get_flattened_data())) for frame, mask in zip(asset_frames, asset_masks)],
            "probe_changed_safe_pixels": safe_changes,
            "probe_changed_protected_pixels": protected_changes,
            "stage3_changed_safe_pixels": pattern_safe_changes,
            "stage3_changed_protected_pixels": pattern_protected_changes,
            "stage3_animation_mismatch_pixels": pattern_animation_mismatches,
            "rare_treatment": asset["rare_treatment"]["id"],
            "stage4_authored_overlay_retention": rare_retention,
            "stage4_changed_rare_safe_pixels": rare_authorized_changes,
            "stage4_minimum_visible_pixels": MIN_RARE_VISIBLE_PIXELS,
            "stage4_changed_outside_rare_safe_pixels":
                rare_unauthorized_changes,
            "stage4_animation_mismatch_pixels": rare_animation_mismatches,
            "frame_checks": frame_checks,
        })

    HEADER_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEADER_PATH.write_text(
        build_header(manifest, palettes, packed_frames, packed_masks, packed_rare, packed_anchors),
        encoding="utf-8",
    )
    palette_preview = make_palette_comparison(manifest, frames, palettes)
    animation_preview = make_animation_comparison(manifest, frames, palettes)
    protection_preview = make_protection_proof(manifest, frames, masks, palettes[0])
    pattern_preview = make_pattern_comparison(
        manifest, frames, masks, rare_overlays, anchors, palettes
    )
    rare_preview = make_rare_comparison(
        manifest, frames, masks, rare_overlays, anchors, palettes
    )
    report = {
        "schema_version": 1,
        "status": "passed",
        "builder": str(BUILDER_PATH.relative_to(ROOT)),
        "builder_sha256": sha256_file(BUILDER_PATH),
        "style": manifest["style"],
        "manifest_sha256": sha256_file(MANIFEST_PATH),
        "semantic_role_count": len(manifest["semantic_roles"]),
        "palette_count": len(palettes),
        "palette_ids": [definition["id"] for definition in manifest["palettes"]],
        "header": str(HEADER_PATH.relative_to(ROOT)),
        "header_sha256": sha256_file(HEADER_PATH),
        "palette_comparison": str(palette_preview.relative_to(ROOT)),
        "palette_comparison_sha256": sha256_file(palette_preview),
        "animation_comparison": str(animation_preview.relative_to(ROOT)),
        "animation_comparison_sha256": sha256_file(animation_preview),
        "protection_proof": str(protection_preview.relative_to(ROOT)),
        "protection_proof_sha256": sha256_file(protection_preview),
        "stage3_pattern_comparison": str(pattern_preview.relative_to(ROOT)),
        "stage3_pattern_comparison_sha256": sha256_file(pattern_preview),
        "stage4_rare_comparison": str(rare_preview.relative_to(ROOT)),
        "stage4_rare_comparison_sha256": sha256_file(rare_preview),
        "total_semantic_bytes": sum(len(data) for values in packed_frames.values() for data in values),
        "total_mask_bytes": sum(len(data) for values in packed_masks.values() for data in values),
        "total_rare_bytes": sum(len(data) for values in packed_rare.values() for data in values),
        "total_anchor_bytes": sum(len(data) * 2 for values in packed_anchors.values() for data in values),
        "assets": reports,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def check() -> dict:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    if report.get("status") != "passed" or sha256_file(MANIFEST_PATH) != report["manifest_sha256"]:
        raise SystemExit("variation manifest changed or report is not passing; rebuild it")
    if report.get("builder") != str(BUILDER_PATH.relative_to(ROOT)) or \
            sha256_file(BUILDER_PATH) != report.get("builder_sha256"):
        raise SystemExit("creature variation builder changed; rebuild it")
    paths = [
        (ROOT / report["header"], report["header_sha256"]),
        (ROOT / report["palette_comparison"], report["palette_comparison_sha256"]),
        (ROOT / report["animation_comparison"], report["animation_comparison_sha256"]),
        (ROOT / report["protection_proof"], report["protection_proof_sha256"]),
        (ROOT / report["stage3_pattern_comparison"], report["stage3_pattern_comparison_sha256"]),
        (ROOT / report["stage4_rare_comparison"], report["stage4_rare_comparison_sha256"]),
    ]
    for asset in report["assets"]:
        paths.append((ROOT / asset["source"], asset["source_sha256"]))
        authored = asset.get("authored_animation")
        if authored:
            paths.extend((
                (ROOT / authored["manifest"], authored["manifest_sha256"]),
                (ROOT / authored["report"], authored["report_sha256"]),
                (
                    ROOT / authored["reviewed_spritesheet"],
                    authored["reviewed_spritesheet_sha256"],
                ),
            ))
        animation_audit = asset.get("animation_audit", {})
        if not animation_audit or not all(animation_audit.values()):
            raise SystemExit(f"animation audit regressed for {asset['id']}")
        if any(asset["probe_changed_protected_pixels"]):
            raise SystemExit(f"protected anatomy audit regressed for {asset['id']}")
        if any(any(values) for values in asset["stage3_changed_protected_pixels"].values()):
            raise SystemExit(f"stage-3 anatomy audit regressed for {asset['id']}")
        if any(asset["stage4_changed_outside_rare_safe_pixels"]):
            raise SystemExit(
                f"stage-4 rare-safe audit regressed for {asset['id']}"
            )
        if not all(all(check.values()) for check in asset["frame_checks"]):
            raise SystemExit(f"stored variation gates are not passing for {asset['id']}")
    for path, expected in paths:
        if not path.exists() or sha256_file(path) != expected:
            raise SystemExit(f"variation artifact hash mismatch: {path}")
    print(
        f"Creature variations verified: {len(report['assets'])} creatures, "
        f"{report['palette_count']} palettes, protected changes=0, "
        f"{report['total_semantic_bytes'] + report['total_mask_bytes'] + report['total_rare_bytes'] + report['total_anchor_bytes']} packed bytes"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="hash-check generated assets and stored protection proof")
    args = parser.parse_args()
    report = check() if args.check else build()
    if not args.check:
        print(
            f"Built {len(report['assets'])} semantic creatures with {report['palette_count']} palettes; "
            "protected probe changes: 0"
        )
        print(report["palette_comparison"])
        print(report["animation_comparison"])
        print(report["protection_proof"])
        print(report["stage3_pattern_comparison"])
        print(report["stage4_rare_comparison"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
