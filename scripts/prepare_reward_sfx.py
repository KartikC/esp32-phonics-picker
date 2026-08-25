#!/usr/bin/env python3
"""Prepare the user-selected Venice reward SFX for the V2 speaker path."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "audio/generated/device-pcm"
MANIFEST = ROOT / "audio/generated/device-audio-manifest.json"
SAMPLE_RATE = 16000
SFX_DURATION_SECONDS = 2.0

DOWNMIX = "pan=mono|c0=0.5*c0+0.5*c1"
BANDPASS = "highpass=f=300:poles=2,lowpass=f=5000:poles=2"
EDGE_FADES = "afade=t=in:st=0:d=0.006,afade=t=out:st=1.97:d=0.03"
RESAMPLE = "aresample=16000:resampler=soxr:precision=28"
PREPROCESS = f"{DOWNMIX},{BANDPASS},{EDGE_FADES}"
BASE_TARGET_LUFS = -28
BASE_TRUE_PEAK_DBTP = -9
CREATURE_GAIN_DB = 1.5


@dataclass(frozen=True)
class RewardSfxSource:
    kind: str
    asset_id: str
    source: str
    source_sha256: str


SOURCES = (
    RewardSfxSource(
        "reward_bubble", "sfx_bubble_round",
        "audio/experiments/venice-sfx-2026-08-24/raw/"
        "shared-bubbles__elevenlabs-sound-effects-v2.mp3",
        "d9b45313bfb55e115644c438431e4d5893d36f45319dc6e4784c535df90e1078",
    ),
    RewardSfxSource(
        "reward_bubble", "sfx_bubble_even",
        "audio/experiments/venice-sfx-2026-08-24/iteration-2/raw/"
        "bubbles-even__elevenlabs-sound-effects-v2.mp3",
        "b6f470a5074068918199c473f8165f96f436cd7fbcb72307e3d0b57796ed6feb",
    ),
    RewardSfxSource(
        "reward_bubble", "sfx_bubble_hollow",
        "audio/experiments/venice-sfx-2026-08-24/iteration-2/raw/"
        "bubbles-large-last__elevenlabs-sound-effects-v2.mp3",
        "da59bbfdd242fa5f90dc5cb2379cbd2bdcbcfb9970a6ae660d32c04821149061",
    ),
    RewardSfxSource(
        "reward_bubble", "sfx_bubble_cascade",
        "audio/experiments/venice-sfx-2026-08-24/iteration-2/raw/"
        "bubbles-cascade__elevenlabs-sound-effects-v2.mp3",
        "dba47d97e79af5a16050715716c5b96ece123d767fff72cafd130990b7a1d931",
    ),
    RewardSfxSource(
        "reward_creature", "sfx_creature_moon_jelly",
        "audio/experiments/venice-sfx-2026-08-24/raw/"
        "moon-jelly__elevenlabs-sound-effects-v2.mp3",
        "efb0f41cdcb3ca1d5b4eb415713a9ee24b1ffefef99637c45d7280d395da0277",
    ),
    RewardSfxSource(
        "reward_creature", "sfx_creature_reef_shark",
        "audio/experiments/venice-sfx-2026-08-24/iteration-2/raw/"
        "shark-pressure-pulse__elevenlabs-sound-effects-v2.mp3",
        "b8949d656c352f34a299ab6b5c295116ebab4615842292db83abbd21c4d10e7c",
    ),
    RewardSfxSource(
        "reward_creature", "sfx_creature_giant_octopus",
        "audio/experiments/venice-sfx-2026-08-24/raw/"
        "giant-octopus__elevenlabs-sound-effects-v2.mp3",
        "285ded7a02b03b0e4c1ce3c640f0524403754932235e77a539e15751ec82f804",
    ),
    RewardSfxSource(
        "reward_creature", "sfx_creature_seahorse",
        "audio/experiments/venice-sfx-2026-08-24/raw/"
        "seahorse__elevenlabs-sound-effects-v2.mp3",
        "96cfdc32a35601a5906301b75e7e0ffc9802a84b5879d88b57e916ade85c7ed4",
    ),
    RewardSfxSource(
        "reward_creature", "sfx_creature_glass_squid",
        "audio/experiments/venice-sfx-2026-08-24/raw/"
        "glass-squid__elevenlabs-sound-effects-v2.mp3",
        "1b4ea37a7476d77b25553beb090311dd078c77dd8bcc21a5e3774f57c1080536",
    ),
    RewardSfxSource(
        "reward_creature", "sfx_creature_anglerfish",
        "audio/experiments/venice-sfx-2026-08-24/raw/"
        "anglerfish__elevenlabs-sound-effects-v2.mp3",
        "b23d2eed46e474280959fcf884f2882a792c159c311d4f31397afe71d7c61f2a",
    ),
    RewardSfxSource(
        "reward_creature", "sfx_creature_sea_angel",
        "audio/experiments/venice-sfx-2026-08-24/raw/"
        "sea-angel__elevenlabs-sound-effects-v2.mp3",
        "05659fa61f1884a83ec62fab1e77bca77f678985b0af36ba9e671a22abefd0dc",
    ),
    RewardSfxSource(
        "reward_creature", "sfx_creature_gulper_eel",
        "audio/experiments/venice-sfx-2026-08-24/raw/"
        "gulper-eel__elevenlabs-sound-effects-v2.mp3",
        "77937b027fbd81b57e1456a03008b8f790db8fd0b56983b00b7440b56b9c8d9f",
    ),
)


def run(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=capture)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def measure(path: Path) -> tuple[float, float]:
    completed = run(
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", "loudnorm=I=-21:TP=-4:LRA=7:print_format=json",
        "-f", "null", "-", capture=True,
    )
    match = re.search(r'\{\s*"input_i".*?\}', completed.stderr, re.S)
    if not match:
        raise RuntimeError(f"could not measure loudness: {path}")
    report = json.loads(match.group(0))
    return float(report["input_i"]), float(report["input_tp"])


def loudnorm_report(path: Path) -> dict[str, str]:
    completed = run(
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", (
            f"{PREPROCESS},loudnorm=I={BASE_TARGET_LUFS}:"
            f"TP={BASE_TRUE_PEAK_DBTP}:LRA=4:print_format=json"
        ),
        "-f", "null", "-", capture=True,
    )
    match = re.search(r'\{\s*"input_i".*?\}', completed.stderr, re.S)
    if not match:
        raise RuntimeError(f"could not measure source loudness: {path}")
    return json.loads(match.group(0))


def probe(path: Path) -> dict[str, int | float]:
    completed = run(
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate,channels,duration",
        "-of", "json", str(path), capture=True,
    )
    stream = json.loads(completed.stdout)["streams"][0]
    return {
        "sample_rate": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "duration_seconds": round(float(stream["duration"]), 3),
    }


def convert(source: Path, destination: Path, kind: str) -> None:
    # Reproduce the matched audition level the user accepted. Creature cues
    # then receive one shared +1.5 dB lift over the four randomized bubble beds.
    # Sparse animal gestures may still measure below the integrated target once
    # their isolated transient reaches the peak ceiling; they are never crushed
    # merely to force a short-term meter match.
    measured = loudnorm_report(source)
    normalize = (
        f"loudnorm=I={BASE_TARGET_LUFS}:TP={BASE_TRUE_PEAK_DBTP}:LRA=4:"
        f"measured_I={measured['input_i']}:"
        f"measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true"
    )
    creature_gain = (
        f",volume={CREATURE_GAIN_DB}dB" if kind == "reward_creature" else ""
    )
    filters = f"{PREPROCESS},{normalize}{creature_gain},{RESAMPLE}"
    run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source), "-af", filters, "-t", str(SFX_DURATION_SECONDS),
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
        str(destination),
    )


def prepare_reward_sfx() -> None:
    manifest = json.loads(MANIFEST.read_text())
    existing = [
        asset for asset in manifest["assets"]
        if asset.get("kind") not in {"reward_bubble", "reward_creature"}
    ]
    if len(existing) != 42:
        raise RuntimeError(
            f"expected 42 speech/phonics assets before reward SFX, got {len(existing)}"
        )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    generated = []
    for item in SOURCES:
        source = ROOT / item.source
        if sha256(source) != item.source_sha256:
            raise RuntimeError(f"reviewed reward source changed: {item.source}")
        destination = OUTPUT / f"{item.asset_id}.wav"
        convert(source, destination, item.kind)
        metrics = probe(destination)
        if metrics != {
            "sample_rate": SAMPLE_RATE,
            "channels": 1,
            "duration_seconds": SFX_DURATION_SECONDS,
        }:
            raise RuntimeError(f"unexpected reward output format: {destination}")
        loudness_lufs, true_peak_dbtp = measure(destination)
        generated.append({
            "kind": item.kind,
            "id": item.asset_id,
            "source": item.source,
            "source_sha256": item.source_sha256,
            "output_sha256": sha256(destination),
            "bytes": destination.stat().st_size,
            **metrics,
            "measured_loudness_lufs": loudness_lufs,
            "measured_true_peak_dbtp": true_peak_dbtp,
        })

    assets = existing + generated
    manifest["version"] = 2
    manifest["playback_status"] = (
        "speech and phonics accepted; reward SFX user-selected and device-leveled"
    )
    manifest["asset_count"] = len(assets)
    manifest["total_bytes"] = sum(asset["bytes"] for asset in assets)
    manifest["assets"] = assets
    manifest.setdefault("speaker_tuning", {})["reward_sfx"] = {
        "bubble_role": "water-rise bed; lower than creature gesture",
        "bubble_program_target_lufs": BASE_TARGET_LUFS,
        "bubble_true_peak_dbtp_ceiling": BASE_TRUE_PEAK_DBTP,
        "creature_role": "species gesture; slightly louder than bubble bed",
        "creature_gain_over_bubbles_db": CREATURE_GAIN_DB,
        "creature_nominal_program_target_lufs": BASE_TARGET_LUFS + CREATURE_GAIN_DB,
        "creature_true_peak_dbtp_ceiling": BASE_TRUE_PEAK_DBTP + CREATURE_GAIN_DB,
        "short_transient_policy": (
            "respect peak ceiling instead of compressing sparse gestures to an integrated target"
        ),
        "mix_offsets_ms": {"praise": 0, "bubble": 400, "creature": 640},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(generated)} reward SFX; manifest now has {len(assets)} assets")
    print(MANIFEST)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare_reward_mixes.py")],
        check=True,
    )


def main() -> None:
    prepare_reward_sfx()


if __name__ == "__main__":
    main()
