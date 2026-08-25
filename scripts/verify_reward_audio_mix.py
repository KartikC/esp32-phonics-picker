#!/usr/bin/env python3
"""Prove the 32 deployed single-stream celebration masters are exact and safe."""

from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from array import array
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCM_DIR = ROOT / "audio/generated/device-pcm"
MANIFEST = ROOT / "audio/generated/device-audio-manifest.json"
REPORT = ROOT / "audio/generated/reward-audio-mix-report.json"
SAMPLE_RATE = 16000
EDGE_FADE_FRAMES = 64
TRAILING_GAP_MS = 40
CELEBRATION_DURATION_MS = 2960
MIX_FRAMES = 42240

PRAISE_IDS = (
    "praise_nice_job",
    "praise_great_work",
    "praise_you_got_it",
    "praise_thats_it",
)
BUBBLE_IDS = (
    "sfx_bubble_round",
    "sfx_bubble_even",
    "sfx_bubble_hollow",
    "sfx_bubble_cascade",
)
CREATURE_IDS = (
    "sfx_creature_moon_jelly",
    "sfx_creature_reef_shark",
    "sfx_creature_giant_octopus",
    "sfx_creature_seahorse",
    "sfx_creature_glass_squid",
    "sfx_creature_anglerfish",
    "sfx_creature_sea_angel",
    "sfx_creature_gulper_eel",
)


def read_pcm(asset_id: str, apply_edge_fade: bool = False) -> list[int]:
    with wave.open(str(PCM_DIR / f"{asset_id}.wav"), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (
            1,
            2,
            SAMPLE_RATE,
        ):
            raise RuntimeError(f"unsupported WAV format: {asset_id}")
        samples = array("h")
        samples.frombytes(source.readframes(source.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    values = list(samples)
    if apply_edge_fade:
        final_index = len(values) - 1
        for index, sample in enumerate(values):
            fade = min(index, final_index - index, EDGE_FADE_FRAMES)
            values[index] = int(sample * fade / EDGE_FADE_FRAMES)
    return values


def build_report() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text())
    mix_assets = [
        asset for asset in manifest["assets"]
        if asset.get("kind") == "reward_mix"
    ]
    if len(mix_assets) != 32:
        raise RuntimeError(f"reward pack requires 32 offline mixes, got {len(mix_assets)}")

    offsets_ms = manifest["speaker_tuning"]["reward_sfx"]["mix_offsets_ms"]
    offsets = {
        role: milliseconds * SAMPLE_RATE // 1000
        for role, milliseconds in offsets_ms.items()
    }
    source_pcm = {
        asset_id: read_pcm(asset_id, apply_edge_fade=True)
        for asset_id in PRAISE_IDS + BUBBLE_IDS + CREATURE_IDS
    }
    worst_peak = 0
    worst_mix: dict[str, str] | None = None
    clipped_samples = 0
    byte_exact = 0
    for bubble_index, bubble_id in enumerate(BUBBLE_IDS):
        for creature_index, creature_id in enumerate(CREATURE_IDS):
            praise_id = PRAISE_IDS[(bubble_index + creature_index) % 4]
            mix_id = f"reward_mix_b{bubble_index}_c{creature_index}"
            expected = [0] * MIX_FRAMES
            layers = (
                (praise_id, offsets["praise"]),
                (bubble_id, offsets["bubble"]),
                (creature_id, offsets["creature"]),
            )
            for asset_id, start in layers:
                for index, sample in enumerate(source_pcm[asset_id]):
                    expected[start + index] += sample
            actual = read_pcm(mix_id)
            if actual != expected:
                raise RuntimeError(f"offline reward payload differs: {mix_id}")
            byte_exact += 1
            peak = max(abs(sample) for sample in expected)
            clipped_samples += sum(abs(sample) > 32767 for sample in expected)
            if peak > worst_peak:
                worst_peak = peak
                worst_mix = {
                    "mix": mix_id,
                    "praise": praise_id,
                    "bubble": bubble_id,
                    "creature": creature_id,
                }

    audio_end_ms = MIX_FRAMES * 1000 // SAMPLE_RATE
    playback_end_ms = audio_end_ms + TRAILING_GAP_MS
    return {
        "schema_version": 2,
        "sample_rate": SAMPLE_RATE,
        "combination_count": 32,
        "runtime_layer_count": 1,
        "byte_exact_composite_count": byte_exact,
        "praise_pairing": "(bubble variant + creature index) modulo 4",
        "mix_offsets_ms": offsets_ms,
        "bubble_precedes_creature_ms": offsets_ms["creature"] - offsets_ms["bubble"],
        "latest_authored_audio_end_ms": audio_end_ms,
        "playback_end_with_silence_ms": playback_end_ms,
        "celebration_duration_ms": CELEBRATION_DURATION_MS,
        "quiet_tail_before_next_round_ms": CELEBRATION_DURATION_MS - playback_end_ms,
        "unclamped_clipped_sample_count": clipped_samples,
        "worst_unclamped_peak_sample": worst_peak,
        "worst_unclamped_peak_dbfs": round(
            20 * math.log10(worst_peak / 32768), 3
        ),
        "worst_mix": worst_mix,
        "level_policy": manifest["speaker_tuning"]["reward_sfx"],
        "status": "passed"
        if clipped_samples == 0 and byte_exact == 32 and
        playback_end_ms <= CELEBRATION_DURATION_MS
        else "failed",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = build_report()
    if args.check:
        if not REPORT.is_file() or json.loads(REPORT.read_text()) != generated:
            raise RuntimeError("reward audio mix report is stale")
    else:
        REPORT.write_text(json.dumps(generated, indent=2) + "\n")
    if generated["status"] != "passed":
        raise RuntimeError("offline reward audio clips or exceeds the celebration")
    print(
        f"Reward audio: {generated['combination_count']} offline mixes, "
        f"peak {generated['worst_unclamped_peak_dbfs']} dBFS, zero clipping"
    )


if __name__ == "__main__":
    main()
