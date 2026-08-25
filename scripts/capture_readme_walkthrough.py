#!/usr/bin/env python3
"""Capture a camera master and serial-timed Phonics Picker walkthrough.

The camera starts before the existing walkthrough driver so its UTC start can
be aligned with the driver's UTC timeline without hand-tuned video offsets.
Capture sessions intentionally live below ignored ``build/`` and are never
reused, which protects prior camera masters from accidental replacement.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = ROOT / "build" / "readme-media-captures"
LOCAL_DEVICE_PYTHON = ROOT / ".venv-device" / "bin" / "python"
WALKTHROUGH = ROOT / "scripts" / "capture_device_game_walkthrough.py"
SESSION_NAME = "capture-session.json"
VIDEO_NAME = "facetime-hd-master.mp4"
TIMELINE_NAME = "walkthrough-timeline.json"
FFMPEG_LOG_NAME = "ffmpeg.log"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path, session_dir: Path) -> dict[str, object]:
    """Return stable, relocatable evidence for one completed artifact."""
    return {
        "path": os.path.relpath(path, session_dir),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def session_directory(requested: Path | None, now: dt.datetime | None = None) -> Path:
    """Choose a fresh ignored capture directory and reject paths outside build."""
    if requested is None:
        instant = now or dt.datetime.now(dt.timezone.utc)
        stamp = instant.strftime("%Y%m%dT%H%M%S.%fZ")
        requested = CAPTURE_ROOT / stamp
    resolved = requested.expanduser().resolve()
    try:
        resolved.relative_to((ROOT / "build").resolve())
    except ValueError as error:
        raise ValueError("capture output must be inside the repository's ignored build/") from error
    return resolved


def avfoundation_input(camera_device: str, audio_device: str) -> str:
    for label, value in (("camera", camera_device), ("audio", audio_device)):
        if not value or ":" in value or "\n" in value:
            raise ValueError(f"{label} device must be a nonempty AVFoundation name without ':'")
    return f"{camera_device}:{audio_device}"


def recorder_command(
    ffmpeg: str,
    video: Path,
    camera_device: str,
    audio_device: str,
    frame_rate: int,
    video_size: str,
    creation_time: str,
) -> list[str]:
    command = [
        ffmpeg,
        "-n",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-thread_queue_size",
        "512",
        "-f",
        "avfoundation",
        "-framerate",
        str(frame_rate),
        "-video_size",
        video_size,
        "-i",
        avfoundation_input(camera_device, audio_device),
        "-map",
        "0:v:0",
    ]
    if audio_device != "none":
        command.extend(["-map", "0:a:0"])
    command.extend([
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-metadata",
        f"creation_time={creation_time}",
        "-movflags",
        "+faststart",
    ])
    if audio_device != "none":
        command.extend(["-c:a", "aac", "-b:a", "128k"])
    command.append(str(video))
    return command


def walkthrough_command(
    device_python: Path,
    port: str,
    timeline: Path,
    lead_in: float,
    tail: float,
) -> list[str]:
    return [
        str(device_python),
        str(WALKTHROUGH),
        "--port",
        port,
        "--timeline",
        str(timeline),
        "--lead-in",
        str(lead_in),
        "--tail",
        str(tail),
    ]


def finalize_recorder(
    process: subprocess.Popen[str],
    graceful_timeout: float = 30.0,
    interrupt_timeout: float = 10.0,
) -> dict[str, object]:
    """Ask ffmpeg to write its trailer before escalating to process signals."""
    method = "already-exited"
    if process.poll() is None:
        method = "stdin-q"
        try:
            if process.stdin is not None:
                process.stdin.write("q\n")
                process.stdin.flush()
            else:  # pragma: no cover - Popen is always configured with a pipe
                raise BrokenPipeError("recorder stdin is unavailable")
        except (BrokenPipeError, OSError, ValueError):
            method = "sigint"
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=graceful_timeout)
        except subprocess.TimeoutExpired:
            method = "sigint"
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=interrupt_timeout)
            except subprocess.TimeoutExpired:
                method = "terminate"
                process.terminate()
                try:
                    process.wait(timeout=interrupt_timeout)
                except subprocess.TimeoutExpired:  # pragma: no cover - last resort
                    method = "kill"
                    process.kill()
                    process.wait(timeout=interrupt_timeout)
    if process.stdin is not None:
        try:
            process.stdin.close()
        except OSError:
            pass
    return {"method": method, "returncode": process.returncode}


def probe_duration(ffprobe: str, video: Path) -> float:
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    duration = float(completed.stdout.strip())
    if duration <= 0:
        raise RuntimeError(f"ffprobe returned an invalid duration for {video}: {duration}")
    return duration


def require_program(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise RuntimeError(f"required program is unavailable: {name}")
    return resolved


def default_device_python() -> Path:
    """Prefer the local device venv, then the interpreter running this tool."""
    if LOCAL_DEVICE_PYTHON.is_file() and os.access(LOCAL_DEVICE_PYTHON, os.X_OK):
        return LOCAL_DEVICE_PYTHON
    return Path(sys.executable).resolve()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Record a FaceTime HD master synchronized to a real game walkthrough",
    )
    result.add_argument("--port", required=True)
    result.add_argument(
        "--device-python",
        type=Path,
        default=default_device_python(),
        help="Python interpreter with pyserial; defaults to .venv-device or this Python",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "fresh directory below build/; default: a timestamped directory below "
            "build/readme-media-captures/"
        ),
    )
    result.add_argument("--camera-device", default="FaceTime HD Camera")
    result.add_argument(
        "--audio-device",
        default="none",
        help="AVFoundation audio device name; 'none' records the silent video master",
    )
    result.add_argument("--frame-rate", type=int, default=30)
    result.add_argument("--video-size", default="1280x720")
    result.add_argument(
        "--camera-warmup",
        type=float,
        default=2.0,
        help="seconds to record before the serial walkthrough preflight begins",
    )
    result.add_argument("--lead-in", type=float, default=1.5)
    result.add_argument("--tail", type=float, default=1.5)
    return result


def main() -> None:
    args = parser().parse_args()
    if args.frame_rate <= 0:
        raise SystemExit("frame-rate must be positive")
    if args.camera_warmup < 0 or args.lead_in < 0 or args.tail < 0:
        raise SystemExit("camera-warmup, lead-in, and tail must be nonnegative")
    try:
        output = session_directory(args.output_dir)
        avfoundation_input(args.camera_device, args.audio_device)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if output.exists():
        raise SystemExit(f"refusing to replace an existing capture directory: {output}")
    output.mkdir(parents=True)

    device_python = args.device_python.expanduser().resolve()
    if not device_python.is_file() or not os.access(device_python, os.X_OK):
        raise SystemExit(
            f"device Python is unavailable: {device_python}; install requirements with it"
        )
    if not WALKTHROUGH.is_file():
        raise SystemExit(f"walkthrough driver is missing: {WALKTHROUGH}")
    try:
        ffmpeg = require_program("ffmpeg")
        ffprobe = require_program("ffprobe")
    except RuntimeError as error:
        raise SystemExit(str(error)) from error

    video = output / VIDEO_NAME
    timeline = output / TIMELINE_NAME
    ffmpeg_log = output / FFMPEG_LOG_NAME
    camera_started_at_utc = utc_now()
    recorder_stop_requested_at_utc = ""
    camera_stopped_at_utc = ""
    recorder: subprocess.Popen[str] | None = None
    finalization: dict[str, object] = {"method": "not-started", "returncode": None}
    failure: BaseException | None = None
    record_command = recorder_command(
        ffmpeg,
        video,
        args.camera_device,
        args.audio_device,
        args.frame_rate,
        args.video_size,
        camera_started_at_utc,
    )
    drive_command = walkthrough_command(
        device_python, args.port, timeline, args.lead_in, args.tail
    )

    with ffmpeg_log.open("w") as log:
        try:
            recorder = subprocess.Popen(
                record_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=log,
                text=True,
            )
            time.sleep(args.camera_warmup)
            returncode = recorder.poll()
            if returncode is not None:
                raise RuntimeError(
                    f"ffmpeg exited during camera warmup with status {returncode}; "
                    f"see {ffmpeg_log}"
                )
            subprocess.run(drive_command, cwd=ROOT, check=True)
        except BaseException as error:
            failure = error
        finally:
            if recorder is not None:
                recorder_stop_requested_at_utc = utc_now()
                finalization = finalize_recorder(recorder)
            camera_stopped_at_utc = utc_now()

    if failure is None and finalization.get("returncode") != 0:
        failure = RuntimeError(
            f"ffmpeg failed with status {finalization.get('returncode')}; see {ffmpeg_log}"
        )

    duration: float | None = None
    if failure is None:
        try:
            if not video.is_file() or video.stat().st_size == 0:
                raise RuntimeError("ffmpeg did not produce a nonempty video master")
            if not timeline.is_file() or timeline.stat().st_size == 0:
                raise RuntimeError("walkthrough did not produce a nonempty timeline")
            duration = probe_duration(ffprobe, video)
        except BaseException as error:
            failure = error

    artifacts: dict[str, object] = {}
    for name, path in (("video", video), ("timeline", timeline), ("ffmpeg_log", ffmpeg_log)):
        if path.is_file():
            artifacts[name] = artifact(path, output)
    if duration is not None and isinstance(artifacts.get("video"), dict):
        artifacts["video"]["duration_seconds"] = round(duration, 6)  # type: ignore[index]

    session: dict[str, Any] = {
        "schema_version": 1,
        "kind": "readme-walkthrough-capture-session",
        "status": "complete" if failure is None else "failed",
        "camera_started_at_utc": camera_started_at_utc,
        "recorder_stop_requested_at_utc": recorder_stop_requested_at_utc,
        "camera_stopped_at_utc": camera_stopped_at_utc,
        "camera": {
            "device": args.camera_device,
            "audio_device": args.audio_device,
            "frame_rate": args.frame_rate,
            "video_size": args.video_size,
            "warmup_seconds": args.camera_warmup,
        },
        "walkthrough": {
            "port": args.port,
            "python": os.path.relpath(device_python, ROOT),
            "driver": os.path.relpath(WALKTHROUGH, ROOT),
            "lead_in_seconds": args.lead_in,
            "tail_seconds": args.tail,
        },
        "commands": {"ffmpeg": record_command, "walkthrough": drive_command},
        "finalization": finalization,
        "artifacts": artifacts,
    }
    if failure is not None:
        session["error"] = {"type": type(failure).__name__, "message": str(failure)}
    session_path = output / SESSION_NAME
    atomic_json(session_path, session)

    if failure is not None:
        print(f"Capture failed; diagnostic session preserved at {session_path}")
        raise failure
    print(f"Capture complete: {session_path}")


if __name__ == "__main__":
    main()
