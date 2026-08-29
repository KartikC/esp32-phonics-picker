#!/usr/bin/env python3
"""Drive every finite production creature variant while a camera records."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "creatures" / "variation" / "variation_manifest.json"
PATTERNS = ("solid", "spots", "stripes", "mottle")
DEFAULT_PALETTES = (0, 1, 2, 4, 5)


def request_line(device: object, command: str, prefix: str,
                 timeout: float = 4.0,
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
        pending.extend(device.read(1024))
        while b"\n" in pending:
            raw, _, pending = pending.partition(b"\n")
            line = raw.rstrip(b"\r").decode("utf-8", "replace")
            if line:
                print(line, flush=True)
            if line.startswith(prefix):
                return line
    raise RuntimeError(f"No {prefix!r} response after {command!r}")


def parse_status(line: str) -> dict[str, str]:
    return dict(
        field.split("=", 1)
        for field in line.removeprefix("[status] ").split()
        if "=" in field
    )


def representative_seed(creature: int, palette: int, pattern: int,
                        rare: bool) -> int:
    return (
        0xC0DEC0DE
        ^ ((creature + 1) * 0x45D9F3B)
        ^ ((palette + 1) * 0x9E3779B9)
        ^ ((pattern + 1) * 0x27D4EB2D)
        ^ (0xA11CE55D if rare else 0)
    ) & 0xFFFFFFFF


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--lead-in", type=float, default=2.0)
    parser.add_argument("--sample-seconds", type=float, default=1.5)
    parser.add_argument("--between-species", type=float, default=0.7)
    parser.add_argument(
        "--creature",
        action="append",
        default=[],
        help=(
            "Limit capture to this manifest creature id; repeat for multiple "
            "creatures. The default remains the complete production catalog."
        ),
    )
    args = parser.parse_args()
    if args.lead_in < 0 or args.sample_seconds < 0.9 or args.between_species < 0:
        raise SystemExit("lead-in/between-species must be nonnegative; samples need >=0.9 s")

    try:
        import serial
    except ImportError as error:
        raise SystemExit(
            "pyserial is required: python3 -m pip install -r requirements.txt"
        ) from error

    manifest = json.loads(MANIFEST.read_text())
    palettes = manifest["palettes"]
    animals = manifest["animals"]
    indexed_animals = list(enumerate(animals))
    if args.creature:
        requested = set(args.creature)
        known = {animal["id"] for animal in animals}
        unknown = sorted(requested - known)
        if unknown:
            raise SystemExit(
                f"Unknown creature id(s): {', '.join(unknown)}; "
                f"choose from {', '.join(sorted(known))}"
            )
        indexed_animals = [
            (index, animal)
            for index, animal in indexed_animals
            if animal["id"] in requested
        ]
    expected_count = sum(
        len(animal.get("automatic_palette_indices", DEFAULT_PALETTES)) * 5
        for _, animal in indexed_animals
    )
    entries: list[dict[str, object]] = []
    started_wall = dt.datetime.now(dt.timezone.utc).isoformat()
    capture_started_wall = ""
    capture_zero = time.monotonic()
    initial_status: dict[str, str] = {}
    final_status: dict[str, str] = {}

    try:
        with serial.Serial(
            args.port, 115200, timeout=0.20, write_timeout=2
        ) as device:
            preflight_status = parse_status(
                request_line(device, "STATUS", "[status] ", 6.0, 1.0)
            )
            if preflight_status.get("standby") == "yes":
                request_line(device, "WAKE", "[power] awake", 6.0)
            request_line(device, "GAME", "[preview] game resumed")
            # GAME intentionally preserves a real celebration. Waiting longer
            # than its 3.28 s maximum guarantees a settled choice round.
            time.sleep(3.6)
            request_line(device, "UNMUTE", "[mute] requested=")
            initial_status = parse_status(
                request_line(device, "STATUS", "[status] ", 6.0, 1.0)
            )
            required = {
                "audio": "ready", "preview": "no", "standby": "no",
                "mute": "off", "usb_data": "yes",
            }
            mismatches = [
                f"{key}={initial_status.get(key)} expected {value}"
                for key, value in required.items()
                if initial_status.get(key) != value
            ]
            if mismatches:
                raise RuntimeError("; ".join(mismatches))

            capture_zero = time.monotonic()
            capture_started_wall = dt.datetime.now(dt.timezone.utc).isoformat()
            print(
                f"[catalog] lead-in={args.lead_in:.3f}s; camera should be recording",
                flush=True,
            )
            time.sleep(args.lead_in)
            for creature_index, animal in indexed_animals:
                allowed_palettes = tuple(
                    animal.get("automatic_palette_indices", DEFAULT_PALETTES)
                )
                for palette_index in allowed_palettes:
                    treatments = tuple(
                        (pattern_index, False, PATTERNS[pattern_index])
                        for pattern_index in range(len(PATTERNS))
                    ) + ((0, True, animal["rare_treatment"]["label"]),)
                    for pattern_index, rare, treatment in treatments:
                        seed = representative_seed(
                            creature_index, palette_index, pattern_index, rare
                        )
                        command = (
                            f"ANIMATE_VARIANT {creature_index} {palette_index} "
                            f"{pattern_index} {int(rare)} {seed}"
                        )
                        acknowledgement = request_line(
                            device, command, "[test] animated reward=", 6.0
                        )
                        expected_fields = (
                            f"reward={animal['id']}",
                            f"palette={palettes[palette_index]['label']}",
                            f"pattern={pattern_index}",
                            f"seed={seed}",
                            f"rare={'yes' if rare else 'no'}",
                        )
                        if not all(value in acknowledgement for value in expected_fields):
                            raise RuntimeError(
                                f"Unexpected acknowledgement for {command}: {acknowledgement}"
                            )
                        start = time.monotonic() - capture_zero
                        entry = {
                            "ordinal": len(entries),
                            "creature_index": creature_index,
                            "creature_id": animal["id"],
                            "creature_label": animal["label"],
                            "base_rarity": animal["base_rarity"],
                            "palette_index": palette_index,
                            "palette_id": palettes[palette_index]["id"],
                            "palette_label": palettes[palette_index]["label"],
                            "pattern_index": pattern_index,
                            "pattern": PATTERNS[pattern_index],
                            "rare": rare,
                            "treatment": treatment,
                            "seed": seed,
                            "start_seconds": round(start, 6),
                            "command": command,
                            "acknowledgement": acknowledgement,
                        }
                        print(
                            f"[catalog] {len(entries) + 1:03d}/{expected_count:03d} "
                            f"{animal['label']} | {palettes[palette_index]['label']} | "
                            f"{treatment}",
                            flush=True,
                        )
                        time.sleep(args.sample_seconds)
                        entry["end_seconds"] = round(
                            time.monotonic() - capture_zero, 6
                        )
                        entries.append(entry)
                request_line(device, "GAME", "[preview] game resumed")
                time.sleep(args.between_species)

            final_status = parse_status(
                request_line(device, "STATUS", "[status] ", 6.0, 1.0)
            )
            for counter in ("reward_clean", "reward_pity"):
                if final_status.get(counter) != initial_status.get(counter):
                    raise RuntimeError(
                        f"catalog changed {counter}: {initial_status.get(counter)} -> "
                        f"{final_status.get(counter)}"
                    )
    finally:
        # A fresh short connection is deliberate: cleanup still runs when a
        # capture acknowledgement or later validation fails.
        try:
            with serial.Serial(
                args.port, 115200, timeout=0.20, write_timeout=2
            ) as cleanup:
                cleanup.write(b"GAME\nUNMUTE\n")
                cleanup.flush()
                time.sleep(0.3)
        except Exception as cleanup_error:  # pragma: no cover - physical fallback
            print(f"[catalog] cleanup warning: {cleanup_error}", flush=True)

    timeline = {
        "schema_version": 1,
        "kind": "production-device-creature-variant-catalog",
        "port": args.port,
        "started_at_utc": started_wall,
        "capture_started_at_utc": capture_started_wall,
        "lead_in_seconds": args.lead_in,
        "sample_seconds": args.sample_seconds,
        "between_species_seconds": args.between_species,
        "selected_creature_ids": [animal["id"] for _, animal in indexed_animals],
        "finite_categorical_variant_count": len(entries),
        "common_variant_count": sum(not entry["rare"] for entry in entries),
        "rare_variant_count": sum(bool(entry["rare"]) for entry in entries),
        "seed_policy": "one deterministic representative seed per categorical combination",
        "initial_status": initial_status,
        "final_status": final_status,
        "entries": entries,
    }
    if len(entries) != expected_count:
        raise RuntimeError(
            f"catalog produced {len(entries)} entries, expected {expected_count}"
        )
    args.timeline.parent.mkdir(parents=True, exist_ok=True)
    args.timeline.write_text(json.dumps(timeline, indent=2) + "\n")
    print(
        f"[catalog] complete: "
        f"{sum(not entry['rare'] for entry in entries)} common + "
        f"{sum(bool(entry['rare']) for entry in entries)} rare = "
        f"{len(entries)}; {args.timeline}",
        flush=True,
    )


if __name__ == "__main__":
    main()
