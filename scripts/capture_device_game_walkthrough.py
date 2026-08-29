#!/usr/bin/env python3
"""Drive and timestamp one representative real DEEP SEA PHONICS TOY V2 round."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path


def request_line(device: object, command: str, prefix: str,
                 timeout: float = 5.0,
                 resend_interval: float | None = None) -> str:
    device.reset_input_buffer()
    deadline = time.monotonic() + timeout
    next_send = 0.0
    pending = bytearray()
    while time.monotonic() < deadline:
        now = time.monotonic()
        if next_send == 0.0 or (
            resend_interval is not None and now >= next_send
        ):
            device.write((command + "\n").encode())
            device.flush()
            next_send = now + (resend_interval or timeout + 1.0)
        pending.extend(device.read_until(b"\n"))
        if b"\n" not in pending:
            continue
        line = bytes(pending).rstrip(b"\r\n").decode("utf-8", "replace")
        pending.clear()
        if line:
            print(line, flush=True)
        if line.startswith(prefix):
            return line
    raise RuntimeError(f"No {prefix!r} response after {command!r}")


def wait_line(device: object, prefix: str, timeout: float = 5.0) -> str:
    """Wait for an unsolicited runtime transition without sending a command."""
    deadline = time.monotonic() + timeout
    pending = bytearray()
    while time.monotonic() < deadline:
        # read_until consumes exactly one serial record, leaving a following
        # [round] line buffered for the next transition wait.
        pending.extend(device.read_until(b"\n"))
        if b"\n" not in pending:
            continue
        line = bytes(pending).rstrip(b"\r\n").decode("utf-8", "replace")
        pending.clear()
        if line:
            print(line, flush=True)
        if line.startswith(prefix):
            return line
    raise RuntimeError(f"No unsolicited {prefix!r} response")


def parse_status(line: str) -> dict[str, str]:
    return dict(
        field.split("=", 1)
        for field in line.removeprefix("[status] ").split()
        if "=" in field
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--timeline", required=True, type=Path)
    parser.add_argument("--lead-in", type=float, default=1.5)
    parser.add_argument("--tail", type=float, default=1.5)
    args = parser.parse_args()
    if args.lead_in < 0 or args.tail < 0:
        raise SystemExit("lead-in and tail must be nonnegative")

    try:
        import serial
    except ImportError as error:
        raise SystemExit(
            "pyserial is required: python3 -m pip install -r requirements.txt"
        ) from error

    events: list[dict[str, object]] = []
    initial_status: dict[str, str] = {}
    final_status: dict[str, str] = {}
    capture_started_at_utc = ""
    capture_zero = time.monotonic()

    def event(device: object, command: str, prefix: str) -> str:
        sent_at = time.monotonic() - capture_zero
        line = request_line(device, command, prefix)
        events.append({
            "command": command,
            "sent_seconds": round(sent_at, 6),
            "ack_seconds": round(time.monotonic() - capture_zero, 6),
            "acknowledgement": line,
        })
        return line

    try:
        with serial.Serial(
            args.port, 115200, timeout=0.20, write_timeout=2
        ) as device:
            preflight = parse_status(
                request_line(device, "STATUS", "[status] ", 6.0, 1.0)
            )
            if preflight.get("standby") == "yes":
                request_line(device, "WAKE", "[power] awake", 6.0)
            request_line(device, "GAME", "[preview] game resumed")
            time.sleep(3.6)
            request_line(device, "UNMUTE", "[mute] requested=")
            initial_status = parse_status(
                request_line(device, "STATUS", "[status] ", 6.0, 1.0)
            )
            required = {
                "audio": "ready", "preview": "no", "standby": "no",
                "mute": "off", "usb_data": "yes", "distinct": "yes",
            }
            mismatches = [
                f"{key}={initial_status.get(key)} expected {value}"
                for key, value in required.items()
                if initial_status.get(key) != value
            ]
            if mismatches:
                raise RuntimeError("; ".join(mismatches))

            capture_started_at_utc = dt.datetime.now(dt.timezone.utc).isoformat()
            capture_zero = time.monotonic()
            print("[walkthrough] camera should be recording", flush=True)
            time.sleep(args.lead_in)
            event(device, "REPLAY", "[replay]")
            time.sleep(3.0)
            wrong_line = event(device, "WRONG", "[choice] wrong")
            wrong_sent_seconds = float(events[-1]["sent_seconds"])
            wrong_black_line = wait_line(
                device, "[transition] wrong black", 3.0
            )
            events.append({
                "command": "WRONG_BLACK",
                "sent_seconds": wrong_sent_seconds,
                "ack_seconds": round(time.monotonic() - capture_zero, 6),
                "acknowledgement": wrong_black_line,
            })
            next_round_line = wait_line(device, "[round] ", 3.0)
            events.append({
                "command": "WRONG_NEXT_ROUND",
                "sent_seconds": wrong_sent_seconds,
                "ack_seconds": round(time.monotonic() - capture_zero, 6),
                "acknowledgement": next_round_line,
            })
            time.sleep(2.0)
            event(device, "REPLAY", "[replay]")
            time.sleep(3.0)
            correct_line = event(device, "ANIMATE", "[choice] correct")
            time.sleep(5.4)
            sent_at = time.monotonic() - capture_zero
            final_line = request_line(
                device, "STATUS", "[status] ", 8.0, 1.0
            )
            events.append({
                "command": "STATUS",
                "sent_seconds": round(sent_at, 6),
                "ack_seconds": round(time.monotonic() - capture_zero, 6),
                "acknowledgement": final_line,
            })
            final_status = parse_status(final_line)
            time.sleep(args.tail)

            if "rare=" not in correct_line or "reward=" not in correct_line:
                raise RuntimeError("correct-choice log omitted reward identity")
            if not wrong_line.startswith("[choice] wrong"):
                raise RuntimeError("wrong-choice path was not exercised")
            previous_target = initial_status.get("target")
            next_target = parse_status(
                next_round_line.replace("[round] ", "[status] ", 1)
            ).get("target")
            if not next_target or next_target == previous_target:
                raise RuntimeError(
                    "wrong choice did not advance to a different target"
                )
            final_required = {
                "audio": "ready", "preview": "no", "standby": "no",
                "mute": "off", "usb_data": "yes", "distinct": "yes",
            }
            final_mismatches = [
                f"{key}={final_status.get(key)} expected {value}"
                for key, value in final_required.items()
                if final_status.get(key) != value
            ]
            if final_mismatches:
                raise RuntimeError("; ".join(final_mismatches))
    finally:
        try:
            with serial.Serial(
                args.port, 115200, timeout=0.20, write_timeout=2
            ) as cleanup:
                cleanup.write(b"GAME\nUNMUTE\n")
                cleanup.flush()
                time.sleep(0.3)
        except Exception as cleanup_error:  # pragma: no cover - physical fallback
            print(f"[walkthrough] cleanup warning: {cleanup_error}", flush=True)

    timeline = {
        "schema_version": 1,
        "kind": "production-device-game-walkthrough",
        "port": args.port,
        "started_at_utc": capture_started_at_utc,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "lead_in_seconds": args.lead_in,
        "tail_seconds": args.tail,
        "initial_status": initial_status,
        "final_status": final_status,
        "transition_contract_ms": {
            "correct_pulse_end": 400,
            "water_rise_end": 640,
            "full_water_end": 2880,
            "water_recede_end": 3160,
            "next_round": 3280,
        },
        "wrong_transition_contract_ms": {
            "feedback_end": 1100,
            "black_beat_duration": 120,
        },
        "events": events,
    }
    args.timeline.parent.mkdir(parents=True, exist_ok=True)
    args.timeline.write_text(json.dumps(timeline, indent=2) + "\n")
    print(f"[walkthrough] complete: {args.timeline}", flush=True)


if __name__ == "__main__":
    main()
