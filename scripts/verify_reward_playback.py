#!/usr/bin/env python3
"""Run two focused audible reward checks without unrelated interaction gates."""

from __future__ import annotations

import argparse

from verify_device import (
    parse_status,
    request_line,
    require_status,
    verify_reward_audio_fields,
    wait_for_status,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    import serial

    with serial.Serial(
        args.port, 115200, timeout=0.25, write_timeout=2
    ) as device:
        request_line(device, b"UNMUTE\n", "[mute] requested=", 6.0, 1.0)
        initial = wait_for_status(device, {
            "audio": "ready",
            "audio_power": "idle",
            "audio_write_failures": "0",
            "standby": "no",
            "mute": "off",
        }, 8.0)

        bubbles: list[str] = []
        for command, rarity in ((b"REWARD\n", "no"), (b"RARE\n", "yes")):
            line = request_line(
                device, command, "[choice] correct", 8.0, 0.75
            )
            if f" rare={rarity} " not in f" {line} ":
                raise RuntimeError(f"reward has wrong rare state: {line}")
            bubbles.append(verify_reward_audio_fields(line))
            wait_for_status(device, {
                "audio": "ready",
                "audio_power": "on",
                "audio_write_failures": "0",
            }, 4.0)
            wait_for_status(device, {
                "audio": "ready",
                "audio_power": "idle",
                "audio_write_failures": "0",
            }, 6.0)

        if bubbles[0] == bubbles[1]:
            raise RuntimeError("bubble SFX repeated on consecutive rewards")
        final = parse_status(request_line(
            device, b"STATUS\n", "[status] ", 6.0, 0.75
        ))
        require_status(final, {
            "audio": "ready",
            "audio_power": "idle",
            "audio_write_failures": "0",
            "standby": "no",
            "mute": "off",
        })
        for counter in ("reward_clean", "reward_pity"):
            if final.get(counter) != initial.get(counter):
                raise RuntimeError(f"diagnostic reward changed {counter}")

    print(
        "Two audible single-stream rewards, exact offline-master mapping, "
        "nonrepeating bubbles, and zero I2S write failures verified."
    )


if __name__ == "__main__":
    main()
