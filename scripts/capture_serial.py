#!/usr/bin/env python3
"""Reconnect across an ESP32-S3 USB reset and timestamp its serial log."""

from __future__ import annotations

import argparse
import glob
import sys
import time

import serial


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--port-glob", default="/dev/cu.usbmodem*")
    args = parser.parse_args()

    started = time.monotonic()
    deadline = started + args.duration
    connection: serial.Serial | None = None
    pending = bytearray()

    while time.monotonic() < deadline:
        if connection is None:
            for port in sorted(glob.glob(args.port_glob)):
                try:
                    connection = serial.Serial(port, 115200, timeout=0.15)
                    print(f"[{time.monotonic() - started:6.2f}] connected {port}")
                    break
                except (OSError, serial.SerialException):
                    connection = None
            if connection is None:
                time.sleep(0.1)
                continue

        try:
            pending.extend(connection.read(1024))
            while b"\n" in pending:
                raw_line, _, pending = pending.partition(b"\n")
                line = raw_line.rstrip(b"\r").decode("utf-8", "replace")
                print(f"[{time.monotonic() - started:6.2f}] {line}")
        except (OSError, serial.SerialException):
            connection.close()
            connection = None
            print(f"[{time.monotonic() - started:6.2f}] disconnected")

    if connection is not None:
        connection.close()
    if pending:
        print(f"[{time.monotonic() - started:6.2f}] {pending.decode('utf-8', 'replace')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
