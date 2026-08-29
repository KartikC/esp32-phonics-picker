#!/usr/bin/env python3
"""Focused regression checks for README capture alignment and media framing."""

from __future__ import annotations

import datetime as dt
import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CAPTURE = load("capture_readme_walkthrough", ROOT / "scripts/capture_readme_walkthrough.py")
BUILD = load("build_readme_media", ROOT / "scripts/build_readme_media.py")


fixed_now = dt.datetime(2026, 8, 25, 12, 34, 56, 123456, tzinfo=dt.timezone.utc)
assert CAPTURE.session_directory(None, fixed_now) == (
    ROOT / "build/readme-media-captures/20260825T123456.123456Z"
)
assert CAPTURE.avfoundation_input("0", "none") == "0:none"
assert CAPTURE.default_device_python().is_file()
assert BUILD.DEFAULT_MUTED.name == "phonics-picker-usb-mute.png"
try:
    CAPTURE.avfoundation_input("bad:camera", "none")
except ValueError:
    pass
else:
    raise AssertionError("AVFoundation delimiter was accepted inside a device name")


class FakeRecorder:
    def __init__(self) -> None:
        self.stdin = FakeInput()
        self.returncode = None
        self.signals: list[int] = []

    def poll(self):
        return self.returncode

    def wait(self, timeout: float):
        self.returncode = 0
        return 0

    def send_signal(self, selected: int) -> None:
        self.signals.append(selected)

    def terminate(self) -> None:
        raise AssertionError("graceful recorder should not be terminated")

    def kill(self) -> None:
        raise AssertionError("graceful recorder should not be killed")


class FakeInput:
    def __init__(self) -> None:
        self.value = ""

    def write(self, value: str) -> None:
        self.value += value

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


recorder = FakeRecorder()
finalized = CAPTURE.finalize_recorder(recorder)
assert finalized == {"method": "stdin-q", "returncode": 0}
assert recorder.stdin.value == "q\n"
assert recorder.signals == []


session = {"camera_started_at_utc": "2026-08-25T12:00:00+00:00"}
timeline = {
    "started_at_utc": "2026-08-25T12:00:02.125000+00:00",
    "transition_contract_ms": {"next_round": 3280},
    "events": [{"command": "ANIMATE", "sent_seconds": 10.25}],
}
assert BUILD.animate_video_seconds(session, timeline) == 12.375
start, end, animate = BUILD.gif_window(session, timeline)
assert abs(start - 11.825) < 1e-9
assert abs(end - 16.505) < 1e-9
assert animate == 12.375
session_with_stop = {
    "camera_started_at_utc": "2026-08-25T12:00:00+00:00",
    "recorder_stop_requested_at_utc": "2026-08-25T12:00:20+00:00",
}
assert BUILD.animate_video_seconds(session_with_stop, timeline, 18.0) == 10.375
start, end, animate = BUILD.gif_window(
    session_with_stop, timeline, source_duration=18.0
)
assert abs(start - 9.825) < 1e-9
assert abs(end - 14.505) < 1e-9
assert animate == 10.375
assert BUILD.parse_crop("280:340:480:190") == (280, 340, 480, 190)

for malformed in ("280x340+480+190", "0:340:480:190", "-1:340:480:190"):
    try:
        BUILD.parse_crop(malformed)
    except ValueError:
        pass
    else:
        raise AssertionError(f"malformed crop was accepted: {malformed}")

with tempfile.TemporaryDirectory() as temporary:
    session_path = Path(temporary) / "capture-session.json"
    video = Path(temporary) / "master.mp4"
    video.write_bytes(b"deterministic-test-video")
    manifest = {
        "artifacts": {
            "video": {
                "path": video.name,
                "bytes": video.stat().st_size,
                "sha256": BUILD.sha256(video),
            }
        }
    }
    assert BUILD.checked_artifact(session_path, manifest, "video") == video.resolve()
    video.write_bytes(b"changed")
    try:
        BUILD.checked_artifact(session_path, manifest, "video")
    except ValueError:
        pass
    else:
        raise AssertionError("changed capture artifact passed hash verification")

print("readme_media_tools_test passed")
