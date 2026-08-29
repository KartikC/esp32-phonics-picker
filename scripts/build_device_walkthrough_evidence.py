#!/usr/bin/env python3
"""Build labeled video and timing frames from a real Photo Booth game walk-through."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


FONT_REGULAR = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
FONT_BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")


def run(command: list[str], capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=capture,
        text=True,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ffmpeg_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def centered(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
             value: str, selected_font: ImageFont.FreeTypeFont,
             fill: str = "white") -> None:
    x0, y0, x1, y1 = box
    bounds = draw.textbbox((0, 0), value, font=selected_font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(((x0 + x1 - width) / 2, (y0 + y1 - height) / 2 - bounds[1]),
              value, font=selected_font, fill=fill)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--timeline", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--video-offset", required=True, type=float)
    parser.add_argument("--crop", default="600:850:660:100")
    parser.add_argument(
        "--camera-label", default="Physical V2 display + camera",
        help="Public-safe label for the camera used to record the board",
    )
    args = parser.parse_args()

    raw = args.video.resolve()
    timeline = json.loads(args.timeline.read_text())
    events = {event["command"]: event for event in timeline["events"]}
    correct = events["ANIMATE"]
    correct_video = args.video_offset + float(correct["sent_seconds"])
    transitions = timeline["transition_contract_ms"]
    replay_events = [event for event in timeline["events"] if event["command"] == "REPLAY"]
    wrong = events["WRONG"]
    wrong_black = events.get("WRONG_BLACK")
    wrong_next = events.get("WRONG_NEXT_ROUND")
    wrong_transition = timeline.get("wrong_transition_contract_ms", {})
    status = events["STATUS"]
    target = str(timeline.get("initial_status", {}).get("target", "?")).upper()
    reward_match = re.search(r"reward=([^ ]+).*palette=([^ ]+(?: [^ ]+)?) pattern=([0-3])",
                             str(correct["acknowledgement"]))
    reward_label = "recorded creature reward"
    if reward_match:
        reward_label = reward_match.group(1).replace("_", " ").title()

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    review = output / "final-game-walkthrough-review.mp4"
    sheet = output / "final-game-walkthrough-timing-contact-sheet.jpg"
    evidence_path = output / "final-game-walkthrough-evidence.json"

    clip_start = args.video_offset + float(replay_events[0]["sent_seconds"]) - 1.0
    clip_end = args.video_offset + float(status["ack_seconds"]) + 2.0
    filters = [
        f"crop={args.crop}",
        "scale=600:850:flags=lanczos",
        "pad=600:990:0:140:color=0x02080c",
        "setpts=PTS-STARTPTS",
        (
            f"drawtext=fontfile='{FONT_BOLD}':text='Real game walkthrough':"
            "fontcolor=white:fontsize=31:x=(w-text_w)/2:y=14"
        ),
    ]

    wrong_black_start = (
        float(wrong_black["ack_seconds"])
        if wrong_black is not None
        else float(wrong["sent_seconds"]) +
        float(wrong_transition.get("feedback_end", 1100)) / 1000.0
    )
    wrong_next_round = (
        float(wrong_next["ack_seconds"])
        if wrong_next is not None
        else wrong_black_start +
        float(wrong_transition.get("black_beat_duration", 120)) / 1000.0
    )
    correct_pulse_end = float(transitions["correct_pulse_end"]) / 1000.0
    water_rise_end = float(transitions["water_rise_end"]) / 1000.0
    full_water_end = float(transitions["full_water_end"]) / 1000.0
    water_recede_end = float(transitions["water_recede_end"]) / 1000.0
    next_round = float(transitions["next_round"]) / 1000.0
    phases = [
        (float(replay_events[0]["sent_seconds"]), float(wrong["sent_seconds"]),
         f"Replay prompt — target {target}"),
        (float(wrong["sent_seconds"]), wrong_black_start,
         "Neutral wrong feedback — input locked"),
        (wrong_black_start, wrong_next_round,
         "Black beat — new challenge prepared"),
        (wrong_next_round, float(replay_events[1]["sent_seconds"]),
         "Fresh challenge after wrong choice"),
        (float(replay_events[1]["sent_seconds"]), float(correct["sent_seconds"]),
         "Replay confirms fresh challenge"),
        (float(correct["sent_seconds"]),
         float(correct["sent_seconds"]) + correct_pulse_end,
         f"Correct card pulse | 0–{transitions['correct_pulse_end']} ms"),
        (float(correct["sent_seconds"]) + correct_pulse_end,
         float(correct["sent_seconds"]) + water_rise_end,
         f"Water rise | {transitions['correct_pulse_end']}–"
         f"{transitions['water_rise_end']} ms"),
        (float(correct["sent_seconds"]) + water_rise_end,
         float(correct["sent_seconds"]) + full_water_end,
         f"{reward_label} + name | full water"),
        (float(correct["sent_seconds"]) + full_water_end,
         float(correct["sent_seconds"]) + water_recede_end,
         f"Creature and name recede | {transitions['full_water_end']}–"
         f"{transitions['water_recede_end']} ms"),
        (float(correct["sent_seconds"]) + water_recede_end,
         float(correct["sent_seconds"]) + next_round,
         f"Fully black beat | "
         f"{transitions['next_round'] - transitions['water_recede_end']} ms"),
        (float(correct["sent_seconds"]) + next_round,
         float(status["ack_seconds"]) + 2.0,
         "Fresh next round"),
    ]
    for start, end, caption in phases:
        relative_start = args.video_offset + start - clip_start
        relative_end = args.video_offset + end - clip_start
        filters.append(
            f"drawtext=fontfile='{FONT_REGULAR}':text='{ffmpeg_text(caption)}':"
            "fontcolor=0x9ddbe2:fontsize=22:x=(w-text_w)/2:y=67:"
            f"enable='between(t\\,{relative_start:.4f}\\,{relative_end:.4f})'"
        )
    filters.append(
        f"drawtext=fontfile='{FONT_REGULAR}':text='{ffmpeg_text(args.camera_label)}':"
        "fontcolor=0xaab8bd:fontsize=18:x=(w-text_w)/2:y=105"
    )
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{clip_start:.6f}", "-t", f"{clip_end - clip_start:.6f}",
        "-i", str(raw), "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(review),
    ])

    recede_sample = full_water_end + (water_recede_end - full_water_end) / 2.0
    black_sample = water_recede_end + (next_round - water_recede_end) / 2.0
    next_round_sample = next_round + 0.14
    timing_samples = [
        (correct_video - 0.35, "Choice round"),
        (correct_video + 0.20, "Correct pulse\n+200 ms"),
        (correct_video + 0.52, "Water rising\n+520 ms"),
        (correct_video + 0.85, "Creature + name\n+850 ms"),
        (correct_video + 1.60, "Full-water hold\n+1600 ms"),
        (correct_video + recede_sample,
         f"Recede\n+{round(recede_sample * 1000)} ms"),
        (correct_video + black_sample,
         f"Black beat\n+{round(black_sample * 1000)} ms"),
        (correct_video + next_round_sample,
         f"Next round\n+{round(next_round_sample * 1000)} ms"),
    ]
    with tempfile.TemporaryDirectory(prefix="walkthrough-evidence-", dir=output) as temp:
        temp_path = Path(temp)
        frames: list[Path] = []
        for index, (timestamp, _) in enumerate(timing_samples):
            frame = temp_path / f"frame-{index:02d}.png"
            run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{timestamp:.6f}", "-i", str(raw),
                "-vf", f"crop={args.crop},scale=300:425:flags=lanczos",
                "-frames:v", "1", str(frame),
            ])
            frames.append(frame)

        tile_w, tile_h, label_h = 300, 425, 72
        margin, header = 12, 116
        canvas = Image.new("RGB", (4 * tile_w + 5 * margin,
                                    header + 2 * (tile_h + label_h + margin)),
                           "#07131c")
        draw = ImageDraw.Draw(canvas)
        title_font = ImageFont.truetype(str(FONT_BOLD), 34)
        label_font = ImageFont.truetype(str(FONT_BOLD), 20)
        body_font = ImageFont.truetype(str(FONT_REGULAR), 18)
        draw.text((18, 15), "Real game transition timing on the V2 AMOLED",
                  font=title_font, fill="#f2f4e8")
        draw.text((18, 65),
                  "Serial timestamp alignment; camera rolling shutter can blend one boundary frame",
                  font=body_font, fill="#a9cad4")
        for index, ((_, caption), frame_path) in enumerate(zip(timing_samples, frames)):
            row, column = divmod(index, 4)
            x = margin + column * (tile_w + margin)
            y = header + row * (tile_h + label_h + margin)
            frame = Image.open(frame_path).convert("RGB")
            frame = ImageOps.fit(frame, (tile_w, tile_h), method=Image.Resampling.LANCZOS)
            canvas.paste(frame, (x, y))
            draw.rectangle((x, y + tile_h, x + tile_w, y + tile_h + label_h),
                           fill="#02080c")
            for line_index, line in enumerate(caption.split("\n")):
                centered(draw,
                         (x, y + tile_h + line_index * 28,
                          x + tile_w, y + tile_h + (line_index + 1) * 28 + 8),
                         line, label_font if line_index == 0 else body_font,
                         "#9ddbe2" if line_index else "#f2f4e8")
        canvas.save(sheet, quality=94, subsampling=0)

    volume = run([
        "ffmpeg", "-hide_banner", "-i", str(raw), "-af", "volumedetect",
        "-f", "null", "-",
    ], capture=True)
    volume_text = volume.stderr
    mean_match = re.search(r"mean_volume: ([^ ]+ dB)", volume_text)
    max_match = re.search(r"max_volume: ([^ ]+ dB)", volume_text)
    evidence = {
        "schema_version": 1,
        "source_video": str(raw),
        "source_video_sha256": sha256(raw),
        "timeline": str(args.timeline.resolve()),
        "timeline_sha256": sha256(args.timeline),
        "video_offset_seconds": args.video_offset,
        "correct_command_video_seconds": correct_video,
        "reward_acknowledgement": correct["acknowledgement"],
        "transition_contract_ms": transitions,
        "audio": {
            "mean_volume": mean_match.group(1) if mean_match else None,
            "max_volume": max_match.group(1) if max_match else None,
        },
        "artifacts": [
            {"path": str(review), "bytes": review.stat().st_size,
             "sha256": sha256(review)},
            {"path": str(sheet), "bytes": sheet.stat().st_size,
             "sha256": sha256(sheet)},
        ],
    }
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"Walk-through evidence complete: {evidence_path}")


if __name__ == "__main__":
    main()
