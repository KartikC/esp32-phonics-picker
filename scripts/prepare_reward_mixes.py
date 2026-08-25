#!/usr/bin/env python3
"""Build the 32 accepted celebrations as offline, single-stream PCM assets."""

from __future__ import annotations

import hashlib
import json
import sys
import wave
from array import array
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCM_DIR = ROOT / "audio/generated/device-pcm"
MANIFEST = ROOT / "audio/generated/device-audio-manifest.json"
SAMPLE_RATE = 16000
EDGE_FADE_FRAMES = 64
MIX_FRAMES = 42240  # 2.64 s: the creature begins at 640 ms and lasts 2 s.
OFFSETS = {"praise": 0, "bubble": 6400, "creature": 10240}

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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_faded_pcm(asset_id: str) -> list[int]:
    path = PCM_DIR / f"{asset_id}.wav"
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (
            1,
            2,
            SAMPLE_RATE,
        ):
            raise RuntimeError(f"unsupported PCM format: {path}")
        samples = array("h")
        samples.frombytes(source.readframes(source.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    values = list(samples)
    final_index = len(values) - 1
    for index, sample in enumerate(values):
        fade = min(index, final_index - index, EDGE_FADE_FRAMES)
        values[index] = int(sample * fade / EDGE_FADE_FRAMES)
    return values


def write_pcm(path: Path, samples: list[int]) -> None:
    payload = array("h", samples)
    if sys.byteorder != "little":
        payload.byteswap()
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(SAMPLE_RATE)
        destination.writeframes(payload.tobytes())


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    source_assets = {
        asset["id"]: asset
        for asset in manifest["assets"]
        if asset.get("kind") != "reward_mix"
    }
    required = PRAISE_IDS + BUBBLE_IDS + CREATURE_IDS
    missing = [asset_id for asset_id in required if asset_id not in source_assets]
    if missing:
        raise RuntimeError(f"accepted reward inputs are missing: {missing}")

    pcm = {asset_id: read_faded_pcm(asset_id) for asset_id in required}
    generated: list[dict[str, object]] = []
    for bubble_index, bubble_id in enumerate(BUBBLE_IDS):
        for creature_index, creature_id in enumerate(CREATURE_IDS):
            # Bubble plus creature selects a balanced praise variant. Every
            # species still reaches all four lines as bubble choices vary,
            # without the 4x storage multiplier that exceeds the partition.
            praise_id = PRAISE_IDS[(bubble_index + creature_index) % 4]
            mix_id = f"reward_mix_b{bubble_index}_c{creature_index}"
            mixed = [0] * MIX_FRAMES
            components = (
                ("praise", praise_id),
                ("bubble", bubble_id),
                ("creature", creature_id),
            )
            for role, asset_id in components:
                start = OFFSETS[role]
                samples = pcm[asset_id]
                if start + len(samples) > MIX_FRAMES:
                    raise RuntimeError(f"{asset_id} exceeds {mix_id}")
                for index, sample in enumerate(samples):
                    mixed[start + index] += sample
            peak = max(abs(sample) for sample in mixed)
            if peak > 32767:
                raise RuntimeError(f"{mix_id} clips at {peak}")

            destination = PCM_DIR / f"{mix_id}.wav"
            write_pcm(destination, mixed)
            generated.append({
                "kind": "reward_mix",
                "id": mix_id,
                "output_sha256": sha256(destination),
                "bytes": destination.stat().st_size,
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
                "duration_seconds": MIX_FRAMES / SAMPLE_RATE,
                "peak_sample": peak,
                "components": [
                    {
                        "role": role,
                        "id": asset_id,
                        "offset_frames": OFFSETS[role],
                        "source_output_sha256": source_assets[asset_id][
                            "output_sha256"
                        ],
                    }
                    for role, asset_id in components
                ],
            })

    base_assets = [
        asset for asset in manifest["assets"]
        if asset.get("kind") != "reward_mix"
    ]
    assets = base_assets + generated
    manifest["version"] = 3
    manifest["playback_status"] = (
        "speech and phonics accepted; reward celebrations offline-mixed for "
        "single-stream device playback"
    )
    manifest["asset_count"] = len(assets)
    manifest["total_bytes"] = sum(int(asset["bytes"]) for asset in assets)
    manifest["assets"] = assets
    reward_tuning = manifest["speaker_tuning"]["reward_sfx"]
    reward_tuning["delivery"] = (
        "32 offline PCM masters; runtime uses the proven one-asset direct streamer"
    )
    reward_tuning["praise_pairing"] = (
        "praise variant = (bubble variant + creature index) modulo 4"
    )
    reward_tuning["deployed_mix_count"] = len(generated)
    reward_tuning["mix_duration_seconds"] = MIX_FRAMES / SAMPLE_RATE
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"Prepared {len(generated)} offline reward mixes; "
        f"manifest now has {len(assets)} assets"
    )
    print(MANIFEST)


if __name__ == "__main__":
    main()
