#!/usr/bin/env python3
"""Turn an untouched Photo Booth catalog master into indexed review evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import tempfile
import textwrap
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
FONT_REGULAR = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
FONT_BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
PATTERN_ORDER = ("solid", "spots", "stripes", "mottle")


def run(command: list[str]) -> None:
    print("[evidence]", " ".join(command[:8]), "...", flush=True)
    subprocess.run(command, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def ffmpeg_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def probe(video: Path) -> tuple[float, float]:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=avg_frame_rate:format=duration",
            "-of", "json", str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    frame_rate = float(Fraction(payload["streams"][0]["avg_frame_rate"]))
    duration = float(payload["format"]["duration"])
    return frame_rate, duration


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def draw_centered(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
                  text: str, selected_font: ImageFont.FreeTypeFont,
                  fill: str = "white") -> None:
    x0, y0, x1, y1 = box
    bounds = draw.textbbox((0, 0), text, font=selected_font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(
        ((x0 + x1 - width) / 2, (y0 + y1 - height) / 2 - bounds[1]),
        text,
        font=selected_font,
        fill=fill,
    )


def build_species_sheet(
    creature_entries: list[dict[str, object]],
    frame_paths: list[Path],
    output: Path,
) -> None:
    by_key = {
        (str(entry["palette_label"]),
         "rare" if entry["rare"] else str(entry["pattern"])):
        (entry, frame_path)
        for entry, frame_path in zip(creature_entries, frame_paths)
    }
    palettes = list(dict.fromkeys(str(entry["palette_label"])
                                  for entry in creature_entries))
    rare_label = str(creature_entries[0]["treatment"])
    for entry in creature_entries:
        if entry["rare"]:
            rare_label = str(entry["treatment"])
            break

    tile_w, tile_h = 300, 425
    left, header, footer = 190, 130, 36
    columns = (*PATTERN_ORDER, "rare")
    canvas = Image.new(
        "RGB",
        (left + len(columns) * tile_w, header + len(palettes) * (tile_h + footer)),
        "#07131c",
    )
    draw = ImageDraw.Draw(canvas)
    title_font = font(FONT_BOLD, 34)
    label_font = font(FONT_BOLD, 22)
    small_font = font(FONT_REGULAR, 18)
    creature = str(creature_entries[0]["creature_label"])
    tier = str(creature_entries[0]["base_rarity"]).capitalize()
    draw.text((22, 18), f"{creature} — {tier} base tier", font=title_font,
              fill="#f2f4e8")
    draw.text(
        (22, 66),
        f"Every production palette × texture; rare motif: {rare_label}",
        font=small_font,
        fill="#a9cad4",
    )
    for column, name in enumerate(columns):
        caption = name.capitalize() if name != "rare" else f"Rare\n{rare_label}"
        lines = caption.split("\n")
        for line_index, line in enumerate(lines):
            draw_centered(
                draw,
                (
                    left + column * tile_w,
                    78 + line_index * 23,
                    left + (column + 1) * tile_w,
                    110 + line_index * 23,
                ),
                line,
                small_font,
                "#f2f4e8",
            )

    for row, palette in enumerate(palettes):
        cell_y = header + row * (tile_h + footer)
        draw_centered(
            draw,
            (8, cell_y, left - 8, cell_y + tile_h),
            palette,
            label_font,
            "#d7e9e7",
        )
        for column, treatment in enumerate(columns):
            entry, frame_path = by_key[(palette, treatment)]
            frame = Image.open(frame_path).convert("RGB")
            frame = ImageOps.fit(frame, (tile_w, tile_h), method=Image.Resampling.LANCZOS)
            x = left + column * tile_w
            canvas.paste(frame, (x, cell_y))
            draw.rectangle((x, cell_y + tile_h, x + tile_w, cell_y + tile_h + footer),
                           fill="#02080c")
            draw_centered(
                draw,
                (x, cell_y + tile_h, x + tile_w, cell_y + tile_h + footer),
                f"#{int(entry['ordinal']) + 1:03d}",
                small_font,
                "#9ddbe2",
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=94, subsampling=0)


def build_overview(
    entries: list[dict[str, object]],
    frame_paths: list[Path],
    output: Path,
) -> None:
    indexed = list(zip(entries, frame_paths))
    creatures = list(dict.fromkeys(str(entry["creature_id"]) for entry in entries))
    tile_w, tile_h = 300, 425
    left, header, footer = 200, 130, 34
    columns = (*PATTERN_ORDER, "rare")
    canvas = Image.new(
        "RGB",
        (left + len(columns) * tile_w, header + len(creatures) * (tile_h + footer)),
        "#07131c",
    )
    draw = ImageDraw.Draw(canvas)
    draw.text((20, 16), "On-device creature modifier overview", font=font(FONT_BOLD, 36),
              fill="#f2f4e8")
    draw.text((20, 66), "One representative of every texture/motif on every species",
              font=font(FONT_REGULAR, 20), fill="#a9cad4")
    for column, value in enumerate(columns):
        draw_centered(
            draw,
            (left + column * tile_w, 86, left + (column + 1) * tile_w, 122),
            value.capitalize(),
            font(FONT_BOLD, 21),
            "#f2f4e8",
        )

    preferred_palette = {"solid": 0, "spots": 1, "stripes": 2, "mottle": 4}
    for row, creature_id in enumerate(creatures):
        candidates = [(entry, path) for entry, path in indexed
                      if entry["creature_id"] == creature_id]
        creature_label = str(candidates[0][0]["creature_label"])
        cell_y = header + row * (tile_h + footer)
        draw_centered(draw, (8, cell_y, left - 8, cell_y + tile_h), creature_label,
                      font(FONT_BOLD, 22), "#d7e9e7")
        for column, treatment in enumerate(columns):
            if treatment == "rare":
                selected = [pair for pair in candidates if pair[0]["rare"]][-1]
            else:
                wanted = preferred_palette[treatment]
                matches = [
                    pair for pair in candidates
                    if not pair[0]["rare"] and pair[0]["pattern"] == treatment
                    and int(pair[0]["palette_index"]) == wanted
                ]
                if not matches:
                    matches = [pair for pair in candidates
                               if not pair[0]["rare"] and pair[0]["pattern"] == treatment]
                selected = matches[0]
            entry, frame_path = selected
            frame = Image.open(frame_path).convert("RGB")
            frame = ImageOps.fit(frame, (tile_w, tile_h), method=Image.Resampling.LANCZOS)
            x = left + column * tile_w
            canvas.paste(frame, (x, cell_y))
            draw.rectangle((x, cell_y + tile_h, x + tile_w, cell_y + tile_h + footer),
                           fill="#02080c")
            caption = f"#{int(entry['ordinal']) + 1:03d}  {entry['palette_label']}"
            draw_centered(draw, (x, cell_y + tile_h, x + tile_w,
                                 cell_y + tile_h + footer), caption,
                          font(FONT_REGULAR, 16), "#9ddbe2")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=94, subsampling=0)


def build_review_clip(
    raw: Path,
    entries: list[dict[str, object]],
    total_entries: int,
    offset: float,
    crop: str,
    output: Path,
) -> None:
    clip_start = offset + float(entries[0]["start_seconds"]) - 0.18
    clip_end = offset + float(entries[-1]["end_seconds"]) + 0.18
    title = (
        f"{entries[0]['creature_label']} | "
        f"{str(entries[0]['base_rarity']).capitalize()} base tier"
    )
    filters = [
        f"crop={crop}",
        "scale=600:850:flags=lanczos",
        "pad=600:970:0:120:color=0x02080c",
        "setpts=PTS-STARTPTS",
        (
            f"drawtext=fontfile='{FONT_BOLD}':text='{ffmpeg_text(title)}':"
            "fontcolor=white:fontsize=28:x=(w-text_w)/2:y=15"
        ),
    ]
    for entry in entries:
        start = offset + float(entry["start_seconds"]) - clip_start
        end = offset + float(entry["end_seconds"]) - clip_start
        modification = (
            str(entry["treatment"]) if entry["rare"] else
            str(entry["pattern"]).capitalize()
        )
        caption = (
            f"#{int(entry['ordinal']) + 1:03d}/{total_entries} | "
            f"{entry['palette_label']} | {modification}"
        )
        filters.append(
            f"drawtext=fontfile='{FONT_REGULAR}':text='{ffmpeg_text(caption)}':"
            "fontcolor=0x9ddbe2:fontsize=23:x=(w-text_w)/2:y=65:"
            f"enable='between(t\\,{start:.4f}\\,{end:.4f})'"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{clip_start:.6f}", "-t", f"{clip_end - clip_start:.6f}",
        "-i", str(raw), "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart", str(output),
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--timeline", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--video-offset", required=True, type=float,
                        help="Raw-video seconds corresponding to timeline second zero")
    parser.add_argument("--crop", default="600:850:660:100")
    args = parser.parse_args()

    raw = args.video.resolve()
    timeline = json.loads(args.timeline.read_text())
    entries = timeline["entries"]
    expected_entries = int(
        timeline.get("finite_categorical_variant_count", len(entries))
    )
    if not entries or len(entries) != expected_entries:
        raise SystemExit(
            f"Expected {expected_entries} nonempty entries, got {len(entries)}"
        )
    frame_rate, duration = probe(raw)
    if args.video_offset + float(entries[-1]["end_seconds"]) >= duration:
        raise SystemExit("Timeline offset places the final sample beyond the video")

    output = args.output_dir.resolve()
    samples_dir = output / "final-creature-samples"
    sheets_dir = output / "final-creature-contact-sheets"
    output.mkdir(parents=True, exist_ok=True)

    index_path = output / "final-all-creature-modifiers-index.tsv"
    with index_path.open("w", newline="") as sink:
        writer = csv.writer(sink, delimiter="\t")
        writer.writerow((
            "ordinal", "creature", "base_tier", "palette", "pattern",
            "rare", "treatment", "seed", "video_start_s", "video_end_s",
            "serial_acknowledgement",
        ))
        for entry in entries:
            writer.writerow((
                int(entry["ordinal"]) + 1,
                entry["creature_label"], entry["base_rarity"],
                entry["palette_label"], entry["pattern"],
                "yes" if entry["rare"] else "no", entry["treatment"],
                entry["seed"],
                f"{args.video_offset + float(entry['start_seconds']):.6f}",
                f"{args.video_offset + float(entry['end_seconds']):.6f}",
                entry["acknowledgement"],
            ))

    with tempfile.TemporaryDirectory(prefix="creature-evidence-", dir=output) as temp:
        temp_path = Path(temp)
        midpoints = [
            args.video_offset +
            (float(entry["start_seconds"]) + float(entry["end_seconds"])) / 2
            for entry in entries
        ]
        frame_numbers = [round(value * frame_rate) for value in midpoints]
        expression = "+".join(f"eq(n\\,{value})" for value in frame_numbers)
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(raw), "-vf",
            f"select='{expression}',crop={args.crop},scale=360:510:flags=lanczos",
            "-fps_mode", "vfr", str(temp_path / "frame-%03d.png"),
        ])
        frame_paths = sorted(temp_path.glob("frame-*.png"))
        if len(frame_paths) != len(entries):
            raise SystemExit(
                f"Extracted {len(frame_paths)} catalog frames, expected {len(entries)}"
            )

        creature_ids = list(dict.fromkeys(str(entry["creature_id"]) for entry in entries))
        review_clips: list[Path] = []
        for creature_index, creature_id in enumerate(creature_ids):
            indices = [index for index, entry in enumerate(entries)
                       if entry["creature_id"] == creature_id]
            creature_entries = [entries[index] for index in indices]
            creature_frames = [frame_paths[index] for index in indices]
            creature_slug = slug(str(creature_entries[0]["creature_label"]))
            sheet = sheets_dir / f"{creature_index:02d}-{creature_slug}-all-modifiers.jpg"
            build_species_sheet(creature_entries, creature_frames, sheet)
            clip = samples_dir / f"{creature_index:02d}-{creature_slug}-all-modifiers.mp4"
            build_review_clip(
                raw,
                creature_entries,
                len(entries),
                args.video_offset,
                args.crop,
                clip,
            )
            review_clips.append(clip)

        overview = output / "final-all-creature-modifiers-overview-contact-sheet.jpg"
        build_overview(entries, frame_paths, overview)

    concat_manifest = output / "final-all-creature-modifiers-review-concat.txt"
    concat_manifest.write_text("".join(
        f"file '{clip.resolve()}'\n" for clip in review_clips
    ))
    combined = output / "final-all-creature-modifiers-review.mp4"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_manifest),
        "-c", "copy", "-movflags", "+faststart", str(combined),
    ])

    artifacts = [index_path, combined,
                 output / "final-all-creature-modifiers-overview-contact-sheet.jpg",
                 *sorted(samples_dir.glob("*.mp4")),
                 *sorted(sheets_dir.glob("*.jpg"))]
    manifest_path = output / "final-all-creature-modifiers-evidence.json"
    evidence = {
        "schema_version": 1,
        "source_video": str(raw),
        "source_video_sha256": sha256(raw),
        "timeline": str(args.timeline.resolve()),
        "timeline_sha256": sha256(args.timeline),
        "video_offset_seconds": args.video_offset,
        "frame_rate": frame_rate,
        "duration_seconds": duration,
        "crop": args.crop,
        "categorical_variants": len(entries),
        "artifacts": [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in artifacts
        ],
    }
    manifest_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"[evidence] complete: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()
