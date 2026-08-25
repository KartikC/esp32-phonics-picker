#!/usr/bin/env python3
"""Prepare clear, gently band-limited 16 kHz mono PCM WAV assets.

The reviewed Cowboy masters keep their phonemes, cadence, and dynamics. The
device pass removes only inaudible speaker extremes, uses two-pass linear
loudness normalization, and never boosts the board's resonant speech bands.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHONICS_SOURCE_SETTING = os.environ.get("PHONICS_SOURCE_DIR")
PHONICS_SOUNDS = Path(PHONICS_SOURCE_SETTING).expanduser() if PHONICS_SOURCE_SETTING else None
RAW_CUES = ROOT / "audio/generated/cowboy-cues/raw"
OUTPUT = ROOT / "audio/generated/device-pcm"
MANIFEST = ROOT / "audio/generated/device-audio-manifest.json"
TARGET_LUFS = -21
TARGET_TRUE_PEAK = -4
SPEAKER_BANDPASS = "highpass=f=300:poles=2,lowpass=f=5000:poles=2"
RESAMPLE = "aresample=16000:resampler=soxr:precision=28"
LEADING_TRIM = (
    "silenceremove=start_periods=1:start_duration=0.010:"
    "start_threshold=-55dB:start_silence=0.015"
)


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def loudnorm_report(source: Path, prefix: str) -> dict[str, str]:
    analysis = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(source),
            "-af", (
                f"{prefix},loudnorm=I={TARGET_LUFS}:TP={TARGET_TRUE_PEAK}:"
                "LRA=7:print_format=json"
            ),
            "-f", "null", "-",
        ],
        check=True, text=True, capture_output=True,
    )
    match = re.search(r'\{\s*"input_i".*?\}', analysis.stderr, re.S)
    if not match:
        raise RuntimeError(f"could not measure loudness: {source}")
    return json.loads(match.group(0))


def two_pass_filter(source: Path, prefix: str) -> str:
    """Return a deterministic linear loudness pass measured after prefix."""
    measured = loudnorm_report(source, prefix)
    normalize = (
        f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TRUE_PEAK}:LRA=7:"
        f"measured_I={measured['input_i']}:"
        f"measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true"
    )
    return f"{prefix},{normalize},{RESAMPLE}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path: Path) -> dict[str, int | float]:
    completed = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels,duration",
            "-of", "json", str(path),
        ],
        check=True, text=True, capture_output=True,
    )
    stream = json.loads(completed.stdout)["streams"][0]
    return {
        "sample_rate": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "duration_seconds": round(float(stream["duration"]), 3),
    }


def convert_phonics(source: Path, destination: Path, gain_db: float) -> None:
    # EBU integrated loudness is unstable for these sub-400 ms phonemes. Keep
    # Preserve the reviewed relative levels and apply one shared peak-safe gain.
    filters = f"{SPEAKER_BANDPASS},{RESAMPLE},volume={gain_db:.3f}dB"
    run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-af", filters,
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(destination),
    )


def convert_cue(source: Path, destination: Path) -> None:
    prefix = f"{LEADING_TRIM},{SPEAKER_BANDPASS}"
    filters = f"{two_pass_filter(source, prefix)},afade=t=in:st=0:d=0.004"
    run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-af", filters, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(destination),
    )


def main() -> None:
    if PHONICS_SOUNDS is None or not PHONICS_SOUNDS.is_dir():
        raise SystemExit("Set PHONICS_SOURCE_DIR to the folder containing the reviewed cowboy_*.m4a files")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    assets = []
    phonics_sources = [
        PHONICS_SOUNDS / f"cowboy_{letter}.m4a"
        for letter in "abcdefghijklmnopqrstuvwxyz"
    ]
    phonics_peak = max(
        float(loudnorm_report(source, f"{SPEAKER_BANDPASS},{RESAMPLE}")["input_tp"])
        for source in phonics_sources
    )
    phonics_gain_db = min(0.0, TARGET_TRUE_PEAK - phonics_peak)
    for letter in "abcdefghijklmnopqrstuvwxyz":
        source = PHONICS_SOUNDS / f"cowboy_{letter}.m4a"
        destination = OUTPUT / f"cowboy_{letter}.wav"
        convert_phonics(source, destination, phonics_gain_db)
        assets.append({
            "kind": "phonics", "id": f"cowboy_{letter}",
            "source_sha256": sha256(source), "output_sha256": sha256(destination),
            "bytes": destination.stat().st_size, **probe(destination),
        })

    cue_corpus = json.loads((ROOT / "audio/cowboy-cues.json").read_text())["cues"]
    for cue_id in cue_corpus:
        source = RAW_CUES / f"{cue_id}.wav"
        if not source.exists():
            raise SystemExit(f"Missing generated Cowboy cue: {source}")
        destination = OUTPUT / f"{cue_id}.wav"
        convert_cue(source, destination)
        assets.append({
            "kind": "speech", "id": cue_id,
            "source_sha256": sha256(source), "output_sha256": sha256(destination),
            "bytes": destination.stat().st_size, **probe(destination),
        })

    report = {
        "version": 1,
        "playback_status": "gentler processing accepted by human listening",
        "format": "PCM signed 16-bit little-endian, mono, 16000 Hz",
        "speaker_tuning": {
            "highpass_hz": 300,
            "lowpass_hz": 5000,
            "equalization": "no resonance notch or presence boost",
            "cue_silence": "leading trim only; internal cadence preserved",
            "normalization": "two-pass linear loudnorm",
            "phonics_gain_db": round(phonics_gain_db, 3),
            "phonics_leveling": "reviewed relative levels preserved; shared peak ceiling",
            "loudness_lufs": TARGET_LUFS,
            "true_peak_dbtp": TARGET_TRUE_PEAK,
        },
        "asset_count": len(assets),
        "total_bytes": sum(asset["bytes"] for asset in assets),
        "assets": assets,
    }
    MANIFEST.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Prepared {len(assets)} assets ({report['total_bytes']} bytes)")
    print(f"Wrote {MANIFEST}")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare_reward_sfx.py")],
        check=True,
    )


if __name__ == "__main__":
    main()
