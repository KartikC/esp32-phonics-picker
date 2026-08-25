#!/usr/bin/env python3
"""Build deterministic review frames from a retained provider animation.

The provider is used for the moving anatomy, but the selected source remains
authoritative everywhere outside the reviewed patch. This script is offline:
it performs no API calls and never spends provider balance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "creatures" / "animation" / "shark_chomp_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def selected_subject(manifest: dict) -> Image.Image:
    source_path = ROOT / manifest["source"]
    if sha256_file(source_path) != manifest["source_sha256"]:
        raise RuntimeError("selected shark source hash changed")
    with Image.open(source_path) as source:
        source.load()
        rgba = source.convert("RGBA")
    canvas = Image.new("RGBA", tuple(manifest["conditioning_canvas"]), (0, 0, 0, 0))
    canvas.alpha_composite(rgba, tuple(manifest["source_offset"]))
    return canvas


def load_provider_frames(manifest: dict) -> tuple[list[Image.Image], dict]:
    generated_dir = ROOT / manifest["output_dir"]
    report_path = generated_dir / "provider_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    frames = []
    for expected_index, record in enumerate(report["frames"]):
        if record["index"] != expected_index:
            raise RuntimeError("provider frame order is not canonical")
        path = ROOT / record["path"]
        if sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"provider frame {expected_index} hash changed")
        with Image.open(path) as image:
            image.load()
            frame = image.convert("RGBA")
        if list(frame.size) != manifest["conditioning_canvas"]:
            raise RuntimeError(f"provider frame {expected_index} has size {frame.size}")
        frames.append(frame)
    return frames, report


def quantize_rgba(source: Image.Image, allowed_hex: list[str]) -> Image.Image:
    allowed = [ImageColor.getrgb(value) for value in allowed_hex]
    output = Image.new("RGBA", source.size, (0, 0, 0, 0))
    pixels = []
    for red, green, blue, alpha in source.get_flattened_data():
        if alpha < 128:
            pixels.append((0, 0, 0, 0))
            continue
        nearest = min(
            allowed,
            key=lambda color: (
                (red - color[0]) ** 2 +
                (green - color[1]) ** 2 +
                (blue - color[2]) ** 2
            ),
        )
        pixels.append((*nearest, 255))
    output.putdata(pixels)
    return output


def connected_component_count(image: Image.Image) -> int:
    width, height = image.size
    opaque = {
        index
        for index, pixel in enumerate(image.get_flattened_data())
        if pixel[3] >= 128
    }
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


def pixel_difference(left: Image.Image, right: Image.Image) -> list[bool]:
    return [
        before != after
        for before, after in zip(
            left.get_flattened_data(), right.get_flattened_data()
        )
    ]


def build_frames(manifest: dict) -> tuple[list[Image.Image], Image.Image, dict]:
    source = selected_subject(manifest)
    provider_frames, provider_report = load_provider_frames(manifest)
    recipe = manifest["review_recipe"]
    patch = Image.new("L", source.size, 0)
    ImageDraw.Draw(patch).polygon(
        [tuple(point) for point in recipe["patch_polygon_conditioning"]],
        fill=255,
    )
    allowed = recipe["allowed_colors"]
    crop_box = tuple(recipe["crop_box_conditioning"])
    frames = []
    for provider_index in recipe["provider_frame_schedule"]:
        if provider_index is None:
            composed = source.copy()
        else:
            generated = quantize_rgba(provider_frames[provider_index], allowed)
            composed = Image.composite(generated, source, patch)
        frames.append(composed.crop(crop_box))
    return frames, patch.crop(crop_box), provider_report


def save_review(manifest_path: Path, manifest: dict, frames: list[Image.Image],
                patch: Image.Image, provider_report: dict) -> Path:
    recipe = manifest["review_recipe"]
    output_dir = ROOT / recipe["reviewed_output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = ROOT / manifest["source"]
    frame_paths = []
    for index, frame in enumerate(frames):
        path = output_dir / f"frame_{index}.png"
        frame.save(path, optimize=True)
        frame_paths.append(path)

    width, height = frames[0].size
    sheet = Image.new("RGBA", (width * len(frames), height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * width, 0))
    sheet_path = output_dir / "reviewed_spritesheet.png"
    sheet.save(sheet_path, optimize=True)

    scale = 3
    contact = Image.new("RGBA", (width * scale * len(frames), height * scale), "#071522")
    for index, frame in enumerate(frames):
        enlarged = frame.resize((width * scale, height * scale), Image.Resampling.NEAREST)
        contact.alpha_composite(enlarged, (index * width * scale, 0))
    contact_path = output_dir / "review_contact_sheet_3x.png"
    contact.convert("RGB").save(contact_path, optimize=True)
    contact_sha256 = sha256_file(contact_path)
    preview_path = output_dir / "review_preview.gif"
    frames[0].save(
        preview_path,
        save_all=True,
        append_images=frames[1:],
        duration=180,
        loop=0,
        disposal=2,
    )

    base = frames[0]
    base_pixels = list(base.get_flattened_data())
    patch_pixels = [value >= 128 for value in patch.get_flattened_data()]
    allowed_rgba = {
        (*ImageColor.getrgb(value), 255) for value in recipe["allowed_colors"]
    }
    mouth_box = tuple(recipe["mouth_probe_box_reviewed"])
    dark_colors = {
        (*ImageColor.getrgb("#071522"), 255),
        (*ImageColor.getrgb("#0B2A3C"), 255),
    }
    dark_counts = [
        sum(pixel in dark_colors for pixel in frame.crop(mouth_box).get_flattened_data())
        for frame in frames
    ]
    frame_records = []
    outside_patch_differences = []
    for index, (frame, path) in enumerate(zip(frames, frame_paths)):
        differences = pixel_difference(base, frame)
        outside = sum(
            changed and not inside
            for changed, inside in zip(differences, patch_pixels)
        )
        outside_patch_differences.append(outside)
        alpha = frame.getchannel("A")
        bbox = alpha.getbbox()
        frame_records.append({
            "index": index,
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256_file(path),
            "alpha_bounds": list(bbox) if bbox else None,
            "opaque_pixels": sum(value >= 128 for value in alpha.get_flattened_data()),
            "connected_components": connected_component_count(frame),
            "changed_pixels_from_frame_zero": sum(differences),
            "changed_pixels_outside_reviewed_patch": outside,
        })

    with Image.open(source_path) as selected_source:
        selected_source.load()
        selected_rgba = selected_source.convert("RGBA")
        source_matches = (
            selected_rgba.size == frames[0].size and
            all(
                expected == actual or
                (expected[3] < 128 and actual[3] < 128)
                for expected, actual in zip(
                    selected_rgba.get_flattened_data(),
                    frames[0].get_flattened_data(),
                )
            )
        )
    checks = {
        "frame_zero_is_exact_selected_source": source_matches,
        "four_reviewed_128px_frames": (
            len(frames) == 4 and all(frame.size == (128, 128) for frame in frames)
        ),
        "half_open_frames_are_identical": (
            frame_paths[1].read_bytes() == frame_paths[3].read_bytes()
        ),
        "changes_are_bounded_to_reviewed_mouth_patch": (
            outside_patch_differences == [0, 0, 0, 0]
        ),
        "all_pixels_use_selected_source_palette": all(
            pixel[3] < 128 or pixel in allowed_rgba
            for frame in frames for pixel in frame.get_flattened_data()
        ),
        "no_frame_touches_canvas_edge": all(
            record["alpha_bounds"] is not None and
            record["alpha_bounds"][0] >= 4 and
            record["alpha_bounds"][1] >= 4 and
            record["alpha_bounds"][2] <= 124 and
            record["alpha_bounds"][3] <= 124
            for record in frame_records
        ),
        "component_count_does_not_increase": all(
            record["connected_components"] <= frame_records[0]["connected_components"]
            for record in frame_records
        ),
        "closed_half_open_half_dark_cavity_schedule": (
            dark_counts[1] > dark_counts[0] and
            dark_counts[2] > dark_counts[1] and
            dark_counts[3] == dark_counts[1]
        ),
        "visual_approval_matches_review_contact": (
            manifest.get("visual_approval", {}).get("status") ==
                "approved_for_device_test" and
            manifest.get("visual_approval", {}).get("contact_sheet_sha256") ==
                contact_sha256
        ),
    }
    report = {
        "schema_version": 1,
        "status": "reviewed_for_device_test" if all(checks.values()) else "failed",
        "manifest": str(manifest_path.relative_to(ROOT)),
        "manifest_sha256": sha256_file(manifest_path),
        "source": manifest["source"],
        "source_sha256": manifest["source_sha256"],
        "provider_report_sha256": sha256_file(
            ROOT / manifest["output_dir"] / "provider_report.json"
        ),
        "provider_balance_cost": provider_report.get("balance_cost"),
        "provider_model": provider_report.get("model"),
        "provider_frame_schedule": recipe["provider_frame_schedule"],
        "frames": frame_records,
        "mouth_dark_pixel_counts": dark_counts,
        "checks": checks,
        "reviewed_spritesheet": str(sheet_path.relative_to(ROOT)),
        "reviewed_spritesheet_sha256": sha256_file(sheet_path),
        "review_contact_sheet": str(contact_path.relative_to(ROOT)),
        "review_contact_sheet_sha256": contact_sha256,
        "review_preview": str(preview_path.relative_to(ROOT)),
        "review_preview_sha256": sha256_file(preview_path),
    }
    report_path = output_dir / "review_report.json"
    write_json(report_path, report)
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f"reviewed animation failed: {failed}")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames, patch, provider_report = build_frames(manifest)
    report_path = save_review(
        manifest_path, manifest, frames, patch, provider_report
    )
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
