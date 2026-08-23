#!/usr/bin/env python3
"""Query the production firmware and fail closed on an incomplete install."""

from __future__ import annotations

import argparse
import sys
import time

def choose_port(requested: str | None, available_ports: object) -> str:
    if requested:
        return requested
    ports = [port.device for port in available_ports.comports()]
    if len(ports) != 1:
        print("Available serial ports:", file=sys.stderr)
        for port in ports:
            print(f"  {port}", file=sys.stderr)
        raise SystemExit("Pass --port; automatic selection requires exactly one port.")
    return ports[0]


def parse_status(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in line.removeprefix("[status] ").split():
        if "=" in field:
            key, value = field.split("=", 1)
            values[key] = value
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--timeout", type=float, default=18.0)
    args = parser.parse_args()
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        print(
            "pyserial is required: python3 -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        raise SystemExit(2)
    port = choose_port(args.port, list_ports)

    deadline = time.monotonic() + args.timeout
    next_query = 0.0
    pending = bytearray()
    status_line = ""
    try:
        with serial.Serial(port, 115200, timeout=0.25, write_timeout=2) as device:
            print(f"Connected to {port}; waiting for production status...")
            while time.monotonic() < deadline:
                now = time.monotonic()
                if now >= next_query:
                    device.write(b"STATUS\n")
                    device.flush()
                    next_query = now + 1.5
                pending.extend(device.read(1024))
                while b"\n" in pending:
                    raw, _, pending = pending.partition(b"\n")
                    line = raw.rstrip(b"\r").decode("utf-8", "replace")
                    if line:
                        print(line)
                    if line.startswith("[status] "):
                        status_line = line
                        break
                if status_line:
                    break
    except (OSError, serial.SerialException) as error:
        print(f"Device verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)

    if not status_line:
        raise SystemExit("No production STATUS response. Check the port, cable, and firmware.")
    status = parse_status(status_line)
    expected = {
        "psram": "8388608",
        "audio": "ready",
        "volume": "100",
        "imu": "ready",
        "preview": "no",
        "standby": "no",
        "distinct": "yes",
    }
    failures = [
        f"{key}={status.get(key, 'missing')} (expected {value})"
        for key, value in expected.items()
        if status.get(key) != value
    ]
    if failures:
        print("Device verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        raise SystemExit(1)
    print("Device runtime verified; complete the manual display, touch, motion, and listening checks.")


if __name__ == "__main__":
    main()
