#!/usr/bin/env python3
"""Verify the separate ocean demo's serial protocol and on-device mask audit."""

from __future__ import annotations

import argparse
import re
import sys
import time

from verify_creature_contract import load_creature_contract


SELFTEST_PATTERN = re.compile(
    r"^\[selftest\] (?P<result>PASS|FAIL) "
    r"creatures=(?P<creatures>\d+) frames=(?P<frames>\d+) "
    r"safe=(?P<safe>\d+) protected=(?P<protected>\d+) "
    r"exercised=(?P<exercised>\d+) invalid_safe=(?P<invalid_safe>\d+) "
    r"protected_changes=(?P<protected_changes>\d+)$"
)
TREATMENT_PATTERN = re.compile(
    r"^\[selftest\] treatments spots=(?P<spots>\d+) "
    r"stripes=(?P<stripes>\d+) mottle=(?P<mottle>\d+) "
    r"rare=(?P<rare>\d+) "
    r"treatment_protected_changes=(?P<treatment_protected_changes>\d+) "
    r"missing_pattern_frames=(?P<missing_pattern_frames>\d+) "
    r"missing_rare_frames=(?P<missing_rare_frames>\d+)$"
)


def wait_for_selftest(
    device: object, timeout: float
) -> tuple[re.Match[str], re.Match[str]]:
    deadline = time.monotonic() + timeout
    next_query = 0.0
    pending = bytearray()
    base_match: re.Match[str] | None = None
    treatment_match: re.Match[str] | None = None
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_query:
            device.write(b"v\n")
            device.flush()
            next_query = now + 1.0
        pending.extend(device.read(1024))
        while b"\n" in pending:
            raw, _, pending = pending.partition(b"\n")
            line = raw.rstrip(b"\r").decode("utf-8", "replace")
            if line:
                print(line)
            base_match = SELFTEST_PATTERN.match(line) or base_match
            treatment_match = TREATMENT_PATTERN.match(line) or treatment_match
            if base_match and treatment_match:
                return base_match, treatment_match
    raise SystemExit(
        "No complete ocean-demo treatment self-test response. "
        "Check the port, cable, and flashed firmware."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="explicit V2 board serial port; never guessed")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    try:
        contract = load_creature_contract()
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise SystemExit(f"Ocean demo creature contract is invalid: {error}")
    try:
        import serial
    except ImportError:
        print("pyserial is required: python3 -m pip install -r requirements.txt", file=sys.stderr)
        raise SystemExit(2)

    try:
        with serial.Serial(args.port, 115200, timeout=0.25, write_timeout=2) as device:
            print(f"Connected to {args.port}; requesting the ocean mask self-test...")
            match, treatment_match = wait_for_selftest(device, args.timeout)
    except (OSError, serial.SerialException) as error:
        raise SystemExit(f"Ocean demo verification failed: {error}")

    values = {key: int(value) for key, value in match.groupdict().items() if key != "result"}
    failures = []
    if match.group("result") != "PASS":
        failures.append("firmware reported FAIL")
    expected = {
        "creatures": contract.creature_count,
        "frames": contract.total_frames,
        "invalid_safe": 0,
        "protected_changes": 0,
    }
    for key, expected_value in expected.items():
        if values[key] != expected_value:
            failures.append(f"{key}={values[key]} (expected {expected_value})")
    for key in ("safe", "protected", "exercised"):
        if values[key] <= 0:
            failures.append(f"{key} must be positive")
    treatment_values = {
        key: int(value) for key, value in treatment_match.groupdict().items()
    }
    for key in ("spots", "stripes", "mottle", "rare"):
        if treatment_values[key] <= 0:
            failures.append(f"{key} treatment must change safe pixels")
    for key in (
        "treatment_protected_changes",
        "missing_pattern_frames",
        "missing_rare_frames",
    ):
        if treatment_values[key] != 0:
            failures.append(f"{key}={treatment_values[key]} (expected 0)")
    if failures:
        print("Ocean demo verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        raise SystemExit(1)

    print(
        "On-device semantic, pattern, and rare-treatment audit passed: "
        f"zero protected changes across {contract.total_frames} frames."
    )
    print(
        "Physical AMOLED comparison is still required; use h to freeze, "
        "t/r/s for treatments, and d for the mask/probe views."
    )


if __name__ == "__main__":
    main()
