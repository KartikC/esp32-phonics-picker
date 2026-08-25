#!/usr/bin/env python3
"""Build deterministic README screenshots and a real-device transition GIF."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = ROOT / "build" / "readme-media-captures"
PREVIEW = ROOT / "scripts" / "preview_on_device.py"
DEFAULT_NORMAL = ROOT / "docs" / "images" / "phonics-picker-ui.png"
DEFAULT_MUTED = ROOT / "docs" / "images" / "phonics-picker-usb-mute.png"
DEFAULT_GIF = ROOT / "docs" / "images" / "phonics-picker-gameplay.gif"
DEFAULT_CROP = "280:340:480:190"
DEFAULT_FPS = 12
DEFAULT_WIDTH = 368
DEFAULT_BEFORE = 0.55
DEFAULT_AFTER = 0.85


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_utc(value: str, label: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is not a valid ISO-8601 timestamp: {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a UTC offset")
    return parsed.astimezone(dt.timezone.utc)


def parse_crop(value: str) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"(\d+):(\d+):(\d+):(\d+)", value)
    if not match:
        raise ValueError("crop must be WIDTH:HEIGHT:X:Y using nonnegative integers")
    width, height, x, y = (int(item) for item in match.groups())
    if width <= 0 or height <= 0:
        raise ValueError("crop width and height must be positive")
    return width, height, x, y


def find_latest_session() -> Path:
    sessions = sorted(CAPTURE_ROOT.glob("*/capture-session.json"), reverse=True)
    for path in sessions:
        try:
            candidate = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if candidate.get("status") == "complete":
            return path
    raise FileNotFoundError(
        "no completed capture session found; run scripts/capture_readme_walkthrough.py first"
    )


def checked_artifact(
    session_path: Path,
    session: dict[str, Any],
    name: str,
) -> Path:
    entry = session.get("artifacts", {}).get(name)
    if not isinstance(entry, dict):
        raise ValueError(f"capture session has no {name!r} artifact")
    relative = entry.get("path")
    expected_hash = entry.get("sha256")
    expected_bytes = entry.get("bytes")
    if not isinstance(relative, str) or not isinstance(expected_hash, str):
        raise ValueError(f"capture session {name!r} evidence is incomplete")
    path = (session_path.parent / relative).resolve()
    try:
        path.relative_to(session_path.parent.resolve())
    except ValueError as error:
        raise ValueError(f"capture session {name!r} path escapes its session directory") from error
    if not path.is_file():
        raise FileNotFoundError(f"capture artifact is missing: {path}")
    actual_bytes = path.stat().st_size
    if isinstance(expected_bytes, int) and actual_bytes != expected_bytes:
        raise ValueError(
            f"capture artifact size mismatch for {path}: {actual_bytes} != {expected_bytes}"
        )
    actual_hash = sha256(path)
    if actual_hash != expected_hash:
        raise ValueError(
            f"capture artifact hash mismatch for {path}: {actual_hash} != {expected_hash}"
        )
    return path


def animate_video_seconds(
    session: dict[str, Any],
    timeline: dict[str, Any],
    source_duration: float | None = None,
) -> float:
    """Map ANIMATE's serial time to camera time, correcting startup latency."""
    timeline_started = parse_utc(
        str(timeline.get("started_at_utc", "")),
        "timeline.started_at_utc",
    )
    events = [event for event in timeline.get("events", []) if event.get("command") == "ANIMATE"]
    if len(events) != 1:
        raise ValueError(f"timeline must contain exactly one ANIMATE event; found {len(events)}")
    try:
        sent_seconds = float(events[0]["sent_seconds"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("ANIMATE event has no numeric sent_seconds") from error
    stop_requested = session.get("recorder_stop_requested_at_utc")
    if source_duration is not None and stop_requested:
        if source_duration <= 0:
            raise ValueError("source video duration must be positive")
        recorder_stopped = parse_utc(
            str(stop_requested),
            "session.recorder_stop_requested_at_utc",
        )
        video_started = recorder_stopped - dt.timedelta(seconds=source_duration)
    else:
        video_started = parse_utc(
            str(session.get("camera_started_at_utc", "")),
            "session.camera_started_at_utc",
        )
    timeline_zero = (timeline_started - video_started).total_seconds()
    if timeline_zero < 0:
        raise ValueError(
            "timeline starts before the recorded camera UTC start; capture alignment is invalid"
        )
    if sent_seconds < 0:
        raise ValueError("ANIMATE sent_seconds must be nonnegative")
    return timeline_zero + sent_seconds


def gif_window(
    session: dict[str, Any],
    timeline: dict[str, Any],
    before: float = DEFAULT_BEFORE,
    after: float = DEFAULT_AFTER,
    source_duration: float | None = None,
) -> tuple[float, float, float]:
    if before < 0 or after < 0:
        raise ValueError("GIF before/after padding must be nonnegative")
    animate = animate_video_seconds(session, timeline, source_duration)
    try:
        next_round_seconds = float(timeline["transition_contract_ms"]["next_round"]) / 1000.0
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("timeline has no numeric next_round transition contract") from error
    if next_round_seconds <= 0:
        raise ValueError("next_round transition time must be positive")
    start = animate - before
    if start < 0:
        raise ValueError(
            f"camera master lacks the requested {before:.3f}s pre-ANIMATE lead-in"
        )
    end = animate + next_round_seconds + after
    return start, end, animate


def probe_video(ffprobe: str, video: Path) -> tuple[int, int, float]:
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(completed.stdout)
    streams = data.get("streams", [])
    if len(streams) != 1:
        raise ValueError(f"expected one video stream in {video}")
    width = int(streams[0]["width"])
    height = int(streams[0]["height"])
    duration = float(data["format"]["duration"])
    if width <= 0 or height <= 0 or duration <= 0:
        raise ValueError(f"ffprobe returned invalid video geometry or duration for {video}")
    return width, height, duration


def run_preview(
    python: str,
    output: Path,
    left: str,
    right: str,
    layout: int,
    battery: str,
    muted: bool,
) -> None:
    command = [
        python,
        str(PREVIEW),
        "--left",
        left,
        "--right",
        right,
        "--layout",
        str(layout),
        "--battery",
        battery,
        "--output",
        str(output),
    ]
    if muted:
        command.append("--muted")
    subprocess.run(command, cwd=ROOT, check=True)


def build_gif(
    ffmpeg: str,
    video: Path,
    output: Path,
    start: float,
    end: float,
    crop: tuple[int, int, int, int],
    fps: int,
    width: int,
) -> None:
    crop_text = ":".join(str(item) for item in crop)
    filters = (
        f"crop={crop_text},"
        f"scale={width}:-2:flags=lanczos,fps={fps},"
        "split[gif_source][palette_source];"
        "[palette_source]palettegen=max_colors=128:stats_mode=diff[palette];"
        "[gif_source][palette]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle"
    )
    subprocess.run(
        [
            ffmpeg,
            "-n",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.6f}",
            "-t",
            f"{end - start:.6f}",
            "-i",
            str(video),
            "-an",
            "-vf",
            filters,
            "-loop",
            "0",
            str(output),
        ],
        check=True,
    )


def output_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build current preview PNGs and a UTC-aligned real-device GIF",
    )
    result.add_argument(
        "--session",
        type=Path,
        help="capture-session.json; default: newest completed ignored capture",
    )
    result.add_argument("--normal-output", type=Path, default=DEFAULT_NORMAL)
    result.add_argument("--muted-output", type=Path, default=DEFAULT_MUTED)
    result.add_argument("--gif-output", type=Path, default=DEFAULT_GIF)
    result.add_argument("--crop", default=DEFAULT_CROP)
    result.add_argument("--fps", type=int, default=DEFAULT_FPS)
    result.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    result.add_argument("--before", type=float, default=DEFAULT_BEFORE)
    result.add_argument("--after", type=float, default=DEFAULT_AFTER)
    result.add_argument("--left", default="a", choices=list("abcdefghijklmnopqrstuvwxyz"))
    result.add_argument("--right", default="m", choices=list("abcdefghijklmnopqrstuvwxyz"))
    result.add_argument("--layout", type=int, default=0, choices=range(6))
    result.add_argument("--battery", default="50")
    result.add_argument(
        "--preview-python",
        default=sys.executable,
        help="Python interpreter with Pillow available for preview_on_device.py",
    )
    return result


def main() -> None:
    args = parser().parse_args()
    if args.fps <= 0 or args.width <= 0:
        raise SystemExit("fps and width must be positive")
    try:
        crop = parse_crop(args.crop)
        session_path = (args.session or find_latest_session()).expanduser().resolve()
        session = json.loads(session_path.read_text())
        if session.get("kind") != "readme-walkthrough-capture-session":
            raise ValueError("session is not a README walkthrough capture")
        if session.get("status") != "complete":
            raise ValueError(f"capture session is not complete: {session.get('status')!r}")
        video = checked_artifact(session_path, session, "video")
        timeline_path = checked_artifact(session_path, session, "timeline")
        timeline = json.loads(timeline_path.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(str(error)) from error

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        raise SystemExit("ffmpeg and ffprobe are required to build README media")
    source_width, source_height, source_duration = probe_video(ffprobe, video)
    try:
        start, end, animate = gif_window(
            session, timeline, args.before, args.after, source_duration
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    crop_width, crop_height, crop_x, crop_y = crop
    if crop_x + crop_width > source_width or crop_y + crop_height > source_height:
        raise SystemExit(
            f"crop {args.crop} exceeds source geometry {source_width}x{source_height}"
        )
    frame_tolerance = 1.0 / args.fps
    if end > source_duration + frame_tolerance:
        raise SystemExit(
            f"camera master ends at {source_duration:.3f}s before requested GIF end {end:.3f}s"
        )
    end = min(end, source_duration)

    destinations = [
        args.normal_output.expanduser().resolve(),
        args.muted_output.expanduser().resolve(),
        args.gif_output.expanduser().resolve(),
    ]
    if len(set(destinations)) != len(destinations):
        raise SystemExit("normal, muted, and GIF outputs must be distinct files")
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)

    staging_root = ROOT / "build" / "readme-media-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=staging_root) as temporary:
        temporary_path = Path(temporary)
        staged_normal = temporary_path / "normal.png"
        staged_muted = temporary_path / "muted.png"
        staged_gif = temporary_path / "gameplay.gif"
        run_preview(
            args.preview_python,
            staged_normal,
            args.left,
            args.right,
            args.layout,
            args.battery,
            False,
        )
        run_preview(
            args.preview_python,
            staged_muted,
            args.left,
            args.right,
            args.layout,
            args.battery,
            True,
        )
        build_gif(
            ffmpeg,
            video,
            staged_gif,
            start,
            end,
            crop,
            args.fps,
            args.width,
        )
        for staged in (staged_normal, staged_muted, staged_gif):
            if not staged.is_file() or staged.stat().st_size == 0:
                raise RuntimeError(f"media build produced no artifact: {staged.name}")
        for staged, destination in zip(
            (staged_normal, staged_muted, staged_gif), destinations
        ):
            os.replace(staged, destination)

    evidence = {
        "session": str(session_path),
        "camera_started_at_utc": session["camera_started_at_utc"],
        "timeline_started_at_utc": timeline["started_at_utc"],
        "animate_video_seconds": round(animate, 6),
        "gif_start_seconds": round(start, 6),
        "gif_end_seconds": round(end, 6),
        "crop": args.crop,
        "fps": args.fps,
        "width": args.width,
        "outputs": [output_evidence(path) for path in destinations],
    }
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
