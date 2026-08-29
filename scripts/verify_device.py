#!/usr/bin/env python3
"""Query the production firmware and fail closed on an incomplete install."""

from __future__ import annotations

import argparse
import sys
import time


BUBBLE_SFX_IDS = {
    "sfx_bubble_round",
    "sfx_bubble_even",
    "sfx_bubble_hollow",
    "sfx_bubble_cascade",
}
BUBBLE_INDEX = {
    "sfx_bubble_round": 0,
    "sfx_bubble_even": 1,
    "sfx_bubble_hollow": 2,
    "sfx_bubble_cascade": 3,
}
PRAISE_IDS = (
    "praise_nice_job",
    "praise_great_work",
    "praise_you_got_it",
    "praise_thats_it",
)
CREATURE_SFX_BY_REWARD = {
    "moon_jelly": "sfx_creature_moon_jelly",
    "reef_shark": "sfx_creature_reef_shark",
    "giant_octopus": "sfx_creature_giant_octopus",
    "seahorse": "sfx_creature_seahorse",
    "glass_squid": "sfx_creature_glass_squid",
    "anglerfish": "sfx_creature_anglerfish",
    "sea_angel": "sfx_creature_sea_angel",
    "gulper_eel": "sfx_creature_gulper_eel",
}
CREATURE_INDEX = {
    reward: index for index, reward in enumerate(CREATURE_SFX_BY_REWARD)
}
COMPLETE_STATUS_KEYS = frozenset({
    "psram", "audio", "audio_power", "audio_idle_downs",
    "audio_write_failures", "volume", "imu", "preview", "standby", "mute",
    "usb_data", "play_state", "play_remaining_s", "break_remaining_s",
    "reward_clean", "reward_pity", "target", "distractor", "distinct",
    "slide_left", "slide_right", "motion_rate",
    "touch_irq_gate", "touch_polls", "power_polls",
})
MINIMUM_VERIFIER_PLAY_REMAINING_SECONDS = 60

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


def status_is_complete(status: dict[str, str]) -> bool:
    """Reject STATUS records interrupted by asynchronous diagnostic logging."""
    return COMPLETE_STATUS_KEYS.issubset(status)


def request_line(
    device: object, command: bytes, prefix: str, timeout: float,
    resend_interval: float | None = None,
) -> str:
    device.reset_input_buffer()
    deadline = time.monotonic() + timeout
    next_send = 0.0
    pending = bytearray()
    while time.monotonic() < deadline:
        now = time.monotonic()
        if next_send == 0.0 or (
            resend_interval is not None and now >= next_send
        ):
            device.write(command)
            device.flush()
            next_send = now + (resend_interval or timeout + 1.0)
        pending.extend(device.read_until(b"\n"))
        if b"\n" not in pending:
            continue
        line = bytes(pending).rstrip(b"\r\n").decode("utf-8", "replace")
        pending.clear()
        if line:
            print(line)
        if line.startswith(prefix):
            return line
    raise RuntimeError(
        f"No {prefix.strip()} response after {command.decode().strip()}"
    )


def wait_for_line(device: object, prefix: str, timeout: float) -> str:
    """Read an unsolicited transition line without disturbing the device."""
    deadline = time.monotonic() + timeout
    pending = bytearray()
    while time.monotonic() < deadline:
        # Stop at one newline so a closely following [round] record remains
        # available to the next wait instead of being dropped with this call's
        # local buffer.
        pending.extend(device.read_until(b"\n"))
        if b"\n" not in pending:
            continue
        line = bytes(pending).rstrip(b"\r\n").decode("utf-8", "replace")
        pending.clear()
        if line:
            print(line)
        if line.startswith(prefix):
            return line
    raise RuntimeError(f"No unsolicited {prefix.strip()} transition")


def require_status(status: dict[str, str], expected: dict[str, str]) -> None:
    failures = [
        f"{key}={status.get(key, 'missing')} (expected {value})"
        for key, value in expected.items()
        if status.get(key) != value
    ]
    if failures:
        raise RuntimeError("; ".join(failures))


def wait_for_status(
    device: object, expected: dict[str, str], timeout: float,
    required_keys: frozenset[str] | set[str] | tuple[str, ...] = (),
) -> dict[str, str]:
    """Poll STATUS until the runtime reaches the requested state."""
    required = set(required_keys)
    deadline = time.monotonic() + timeout
    last_status: dict[str, str] = {}
    while time.monotonic() < deadline:
        last_status = parse_status(request_line(
            device, b"STATUS\n", "[status] ", 2.0, 0.5
        ))
        if (required.issubset(last_status) and
                all(last_status.get(key) == value
                    for key, value in expected.items())):
            return last_status
        time.sleep(0.20)
    require_status(last_status, expected)
    missing = sorted(required.difference(last_status))
    raise RuntimeError(
        "STATUS is missing required fields: " + ", ".join(missing)
    )


def verify_reward_audio_fields(line: str) -> str:
    fields = {
        key: value
        for token in line.split()
        if "=" in token
        for key, value in (token.split("=", 1),)
    }
    bubble = fields.get("bubble")
    reward = fields.get("reward")
    creature_sfx = fields.get("creature_sfx")
    if bubble not in BUBBLE_SFX_IDS:
        raise RuntimeError(f"reward reported invalid bubble SFX: {bubble}")
    if CREATURE_SFX_BY_REWARD.get(reward) != creature_sfx:
        raise RuntimeError(
            f"reward {reward} reported mismatched creature SFX: {creature_sfx}"
        )
    bubble_index = BUBBLE_INDEX[bubble]
    creature_index = CREATURE_INDEX[reward]
    expected_praise = PRAISE_IDS[(bubble_index + creature_index) % 4]
    if fields.get("praise") != expected_praise:
        raise RuntimeError(
            f"reward reported praise={fields.get('praise')}, "
            f"expected {expected_praise}"
        )
    expected_mix = f"reward_mix_b{bubble_index}_c{creature_index}"
    if fields.get("reward_mix") != expected_mix:
        raise RuntimeError(
            f"reward reported mix={fields.get('reward_mix')}, "
            f"expected {expected_mix}"
        )
    return bubble


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

    final_status: dict[str, str] = {}
    try:
        with serial.Serial(port, 115200, timeout=0.25, write_timeout=2) as device:
            print(f"Connected to {port}; verifying production runtime...")
            try:
                # Establish a known safe starting state in case a previous
                # maintenance session ended while the data cable remained in.
                request_line(
                    device, b"UNMUTE\n", "[mute] requested=", 6.0, 1.0
                )
                initial = wait_for_status(device, {
                    "psram": "8388608",
                    "audio": "ready",
                    "audio_write_failures": "0",
                    "volume": "90",
                    "imu": "ready",
                    "preview": "no",
                    "standby": "no",
                    "mute": "off",
                    "usb_data": "yes",
                    "play_state": "playing",
                    "break_remaining_s": "0",
                    "distinct": "yes",
                    "touch_irq_gate": "yes",
                }, args.timeout, COMPLETE_STATUS_KEYS)
                for counter in (
                    "reward_clean", "reward_pity", "audio_idle_downs",
                    "play_remaining_s", "touch_polls", "power_polls",
                ):
                    if counter not in initial:
                        raise RuntimeError(f"STATUS is missing {counter}")
                play_remaining_seconds = int(initial["play_remaining_s"])
                if not 1 <= play_remaining_seconds <= 600:
                    raise RuntimeError(
                        "play allowance is outside the expected 1..600 seconds"
                    )
                if play_remaining_seconds < (
                    MINIMUM_VERIFIER_PLAY_REMAINING_SECONDS
                ):
                    raise RuntimeError(
                        "only "
                        f"{play_remaining_seconds}s of play allowance remains; "
                        "power-cycle the device before verification so the "
                        "30-minute break cannot begin during this test"
                    )
                if initial.get("audio_power") not in {"on", "idle"}:
                    raise RuntimeError(
                        f"unexpected initial audio_power={initial.get('audio_power')}"
                    )

                # A replay must synchronously wake the idle codec before PCM
                # is queued, then the complete output path must shut down again
                # after the authored cue plus its 750 ms silent tail.
                request_line(device, b"REPLAY\n", "[replay] ", 4.0)
                active_audio = wait_for_status(device, {
                    "audio": "ready", "audio_power": "on"
                }, 4.0)
                idle_audio = wait_for_status(device, {
                    "audio": "ready", "audio_power": "idle"
                }, 8.0, {"audio_idle_downs", "touch_polls", "power_polls"})
                idle_audio_observed_at = time.monotonic()
                if int(idle_audio["audio_idle_downs"]) <= int(
                    initial["audio_idle_downs"]
                ):
                    raise RuntimeError("audio did not record an idle power-down")

                # With no finger present, the CST820 safety poll should run at
                # roughly 16 Hz rather than the old ~125 Hz continuous traffic.
                time.sleep(0.40)
                quiet_poll = wait_for_status(device, {
                    "touch_irq_gate": "yes"
                }, 4.0, {"touch_polls", "power_polls"})
                quiet_poll_observed_at = time.monotonic()
                touch_delta = int(quiet_poll["touch_polls"]) - int(
                    idle_audio["touch_polls"]
                )
                power_delta = int(quiet_poll["power_polls"]) - int(
                    idle_audio["power_polls"]
                )
                poll_interval = quiet_poll_observed_at - idle_audio_observed_at
                touch_rate = touch_delta / poll_interval
                power_rate = power_delta / poll_interval
                if not 7.5 <= touch_rate <= 30.0:
                    raise RuntimeError(
                        "idle touch polling cadence out of range: "
                        f"{touch_rate:.1f} reads/s over {poll_interval:.2f}s"
                    )
                if not 20.0 <= power_rate <= 75.0:
                    raise RuntimeError(
                        "PWR polling cadence out of range: "
                        f"{power_rate:.1f} reads/s over {poll_interval:.2f}s"
                    )

                # A real wrong choice must play the neutral cue once, lock the
                # answered round, expose the complete black transition, and
                # then announce a different target. It resets clean progress
                # exactly once while preserving the slower pity counter.
                previous_target = initial["target"]
                previous_pity = initial["reward_pity"]
                wrong_line = request_line(
                    device, b"WRONG\n", "[choice] wrong", 4.0
                )
                if " variant=0" not in wrong_line:
                    raise RuntimeError(
                        "wrong choice did not use the neutral response"
                    )
                request_line(
                    device, b"REPLAY\n",
                    "[transition] wrong-answer advance in progress", 2.0
                )
                wait_for_line(device, "[transition] wrong black", 4.0)
                wrong_black_observed_at = time.monotonic()
                next_round_line = wait_for_line(device, "[round] ", 4.0)
                observed_black_seconds = (
                    time.monotonic() - wrong_black_observed_at
                )
                if observed_black_seconds < 0.10:
                    raise RuntimeError(
                        "wrong-answer black beat was too short: "
                        f"{observed_black_seconds * 1000:.1f} ms observed"
                    )
                next_round = parse_status(
                    next_round_line.replace("[round] ", "[status] ", 1)
                )
                next_target = next_round.get("target")
                if not next_target or next_target == previous_target:
                    raise RuntimeError(
                        "wrong choice did not advance to a different target"
                    )
                rarity_baseline = wait_for_status(device, {
                    "audio": "ready", "audio_power": "idle",
                    "audio_write_failures": "0", "reward_clean": "0",
                    "reward_pity": previous_pity, "target": next_target,
                }, 8.0, COMPLETE_STATUS_KEYS)

                # Exercise two complete, audible production celebrations. The
                # line proves the selected four-way bubble, species-matched
                # creature cue, and offline master; audio_power=on proves the
                # one-asset command woke and entered the real output path.
                # Immediate bubble repeats
                # are forbidden by the independent reward-audio selector.
                common_line = request_line(
                    device, b"REWARD\n", "[choice] correct", 4.0
                )
                if " rare=no " not in f" {common_line} ":
                    raise RuntimeError("forced common reward did not report rare=no")
                common_bubble = verify_reward_audio_fields(common_line)
                wait_for_status(device, {
                    "audio": "ready", "audio_power": "on"
                }, 4.0)
                wait_for_status(device, {
                    "audio": "ready", "audio_power": "idle"
                }, 6.0)

                rare_line = request_line(
                    device, b"RARE\n", "[choice] correct", 4.0
                )
                if " rare=yes " not in f" {rare_line} ":
                    raise RuntimeError("forced rare reward did not report rare=yes")
                rare_bubble = verify_reward_audio_fields(rare_line)
                if rare_bubble == common_bubble:
                    raise RuntimeError("bubble SFX repeated on consecutive rewards")
                wait_for_status(device, {
                    "audio": "ready", "audio_power": "on"
                }, 4.0)
                wait_for_status(device, {
                    "audio": "ready", "audio_power": "idle"
                }, 6.0)

                # From this point onward cleanup must assume the first MUTE may
                # have applied even if its acknowledgement is lost.
                request_line(
                    device, b"MUTE\n", "[mute] requested=", 4.0, 1.0
                )
                muted = wait_for_status(device, {
                    "audio": "muted", "audio_power": "suspended",
                    "mute": "on", "usb_data": "yes"
                }, 4.0)

                # Exercise the exact production break renderer without aging
                # or clearing the real play-limit state. GAME exits this USB
                # preview but can never bypass an actual break.
                held_break = request_line(
                    device, b"HOLD_BREAK 900\n", "[test] held break=", 4.0
                )
                if "held break=15:00 remaining_s=900" not in held_break:
                    raise RuntimeError("held break renderer reported the wrong time")
                request_line(
                    device, b"GAME\n", "[preview] game resumed", 4.0
                )

                # Exercise the exact production renderer for every base
                # species and every authored rare treatment. These commands
                # freeze a full-water reward frame, making the same path
                # available for simultaneous camera inspection without
                # changing either rarity-progress counter.
                roster = (
                    "moon_jelly", "reef_shark", "giant_octopus", "seahorse",
                    "glass_squid", "anglerfish", "sea_angel", "gulper_eel",
                )
                restricted_palettes = {
                    "glass_squid": {"Tide slate", "Kelp green", "Moon pale"},
                    "sea_angel": {"Tide slate", "Kelp green", "Moon pale"},
                }
                all_automatic_palettes = {
                    "Tide slate", "Kelp green", "Coral rust", "Sand gold",
                    "Moon pale",
                }
                for rare in (False, True):
                    for index, creature_id in enumerate(roster):
                        command_name = (
                            "HOLD_RARE_CREATURE" if rare else "HOLD_CREATURE"
                        )
                        held_line = request_line(
                            device,
                            f"{command_name} {index}\n".encode(),
                            "[test] held reward=",
                            4.0,
                        )
                        if f"held reward={creature_id} " not in held_line:
                            raise RuntimeError(
                                f"exact creature {index} rendered as the wrong species"
                            )
                        expected_rare = "yes" if rare else "no"
                        if f" rare={expected_rare} " not in f" {held_line} ":
                            raise RuntimeError(
                                f"{creature_id} held reward has wrong rare state"
                            )
                        palette_field = held_line.split(" palette=", 1)[1]
                        palette = palette_field.split(" pattern=", 1)[0]
                        allowed = restricted_palettes.get(
                            creature_id, all_automatic_palettes
                        )
                        if palette not in allowed:
                            raise RuntimeError(
                                f"{creature_id} used disallowed palette {palette}"
                            )
                request_line(
                    device, b"GAME\n", "[preview] game resumed", 4.0
                )

                request_line(
                    device, b"UNMUTE\n", "[mute] requested=", 4.0, 1.0
                )
                resumed = wait_for_status(device, {
                    "audio": "ready", "mute": "off", "usb_data": "yes",
                    "preview": "no", "audio_power": "on",
                }, 4.0)
                final_status = wait_for_status(device, {
                    "audio": "ready", "mute": "off", "usb_data": "yes",
                    "preview": "no", "audio_power": "idle",
                    "audio_write_failures": "0",
                }, 4.0, {"reward_clean", "reward_pity"})
                for counter in ("reward_clean", "reward_pity"):
                    if final_status.get(counter) != rarity_baseline.get(counter):
                        raise RuntimeError(
                            f"diagnostic rewards changed {counter}: "
                            f"{rarity_baseline.get(counter, 'missing')} -> "
                            f"{final_status.get(counter, 'missing')}"
                        )
            finally:
                try:
                    device.write(b"UNMUTE\n")
                    device.flush()
                    time.sleep(0.25)
                except (OSError, serial.SerialException):
                    pass
    except (OSError, serial.SerialException, RuntimeError) as error:
        print(f"Device verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
    if not final_status:
        raise SystemExit("Production verification did not reach its final status gate.")
    print(
        "Device runtime, audio wake/idle state transition, reduced idle "
        "I2C polling, locked neutral wrong-answer advancement with a timed "
        "black beat, "
        "two audible single-stream reward paths, four-way bubble selection, "
        "species-matched SFX, serial mute path, break-timer diagnostic path, "
        "all eight common/rare render "
        "paths, palette "
        "restrictions, and unchanged rarity counters verified; "
        "complete the manual disconnect, double-tap, display, ten-minute "
        "trigger, lockout, standby aging, expiry, touch, motion, and listening "
        "checks."
    )


if __name__ == "__main__":
    main()
