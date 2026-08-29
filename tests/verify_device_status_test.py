#!/usr/bin/env python3
"""Regression coverage for asynchronously interrupted STATUS records."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_device", ROOT / "scripts/verify_device.py"
)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("could not load scripts/verify_device.py")
VERIFY_DEVICE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY_DEVICE)


complete = (
    "[status] psram=8388608 audio=ready audio_power=idle "
    "audio_idle_downs=4 audio_write_failures=0 volume=90 imu=ready "
    "preview=no standby=no mute=off usb_data=yes play_state=playing "
    "play_remaining_s=597 break_remaining_s=0 reward_clean=0 reward_pity=0 "
    "target=q distractor=b distinct=yes slide_left=0,0 "
    "slide_right=0,0 motion_rate=120,116 touch_irq_gate=yes "
    "touch_polls=463 power_polls=1236"
)
parsed = VERIFY_DEVICE.parse_status(complete)
assert VERIFY_DEVICE.status_is_complete(parsed)
assert parsed["audio_power"] == "idle"
assert parsed["play_remaining_s"] == "597"
assert parsed["touch_polls"] == "463"
assert VERIFY_DEVICE.MINIMUM_VERIFIER_PLAY_REMAINING_SECONDS == 60

interrupted = complete.split(" motion_rate=", 1)[0] + " mot[battery] connected=yes"
parsed_interrupted = VERIFY_DEVICE.parse_status(interrupted)
assert parsed_interrupted["audio_power"] == "idle"
assert not VERIFY_DEVICE.status_is_complete(parsed_interrupted)

firmware = (ROOT / "firmware/PhonicsGame/PhonicsGame.ino").read_text()
status_handler = firmware.split('if (command == "STATUS") {', 1)[1].split(
    'if (command == "FRAME") {', 1
)[0]
assert "USBSerial.setTxTimeoutMs(25);" in status_handler
assert "USBSerial.flush();" in status_handler
assert status_handler.rfind("USBSerial.setTxTimeoutMs(0);") > status_handler.rfind(
    "USBSerial.flush();"
)

print("verify_device_status_test passed")
