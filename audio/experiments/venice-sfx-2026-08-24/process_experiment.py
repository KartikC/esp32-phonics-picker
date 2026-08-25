#!/usr/bin/env python3
"""Build non-canonical device-format previews for the Venice SFX audition."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
PREVIEW = ROOT / "device-preview"
ANALYSIS = ROOT / "analysis"
MANIFEST = ROOT / "results.json"
SPECIES_REEL = ROOT / "species-audition-reel.wav"
COMPARISON_REEL = ROOT / "model-comparison-reel.wav"

TARGET_LUFS = -28
TARGET_TRUE_PEAK = -9
TARGET_DURATION_SECONDS = 2.0
BANDPASS = "highpass=f=300:poles=2,lowpass=f=5000:poles=2"
EDGE_FADES = "afade=t=in:st=0:d=0.006,afade=t=out:st=1.97:d=0.03"
DOWNMIX = "pan=mono|c0=0.5*c0+0.5*c1"
PREPROCESS = f"{DOWNMIX},{BANDPASS},{EDGE_FADES}"
RESAMPLE = "aresample=16000:resampler=soxr:precision=28"


def run(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=capture)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path: Path) -> dict[str, int | float | str]:
    completed = run(
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels,duration",
        "-show_entries", "format=duration,size", "-of", "json", str(path),
        capture=True,
    )
    data = json.loads(completed.stdout)
    stream = data["streams"][0]
    audio_format = data["format"]
    return {
        "codec": stream["codec_name"],
        "sample_rate": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "duration_seconds": round(float(audio_format["duration"]), 6),
        "bytes": int(audio_format["size"]),
    }


def loudnorm_report(path: Path, prefix: str) -> dict[str, str]:
    completed = run(
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", (
            f"{prefix},loudnorm=I={TARGET_LUFS}:TP={TARGET_TRUE_PEAK}:"
            "LRA=4:print_format=json"
        ),
        "-f", "null", "-", capture=True,
    )
    match = re.search(r'\{\s*"input_i".*?\}', completed.stderr, re.S)
    if not match:
        raise RuntimeError(f"could not measure loudness: {path}")
    return json.loads(match.group(0))


def convert(source: Path, destination: Path) -> None:
    measured = loudnorm_report(source, PREPROCESS)
    normalize = (
        f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TRUE_PEAK}:LRA=4:"
        f"measured_I={measured['input_i']}:"
        f"measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true"
    )
    filters = f"{PREPROCESS},{normalize},{RESAMPLE}"
    run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source), "-af", filters, "-t", str(TARGET_DURATION_SECONDS),
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destination),
    )


def make_analysis(path: Path, stem: str) -> None:
    run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-lavfi",
        "showspectrumpic=s=1200x500:legend=1:color=viridis:scale=log:"
        "fscale=log:gain=4",
        str(ANALYSIS / f"{stem}__device-spectrogram.png"),
    )
    run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-filter_complex", "showwavespic=s=1200x260:colors=0x49d6c8:scale=sqrt",
        "-frames:v", "1", str(ANALYSIS / f"{stem}__device-waveform.png"),
    )


def build_reel(paths: list[Path], destination: Path, gap_seconds: float) -> None:
    silence = b"\x00\x00" * round(16000 * gap_seconds)
    chunks: list[bytes] = []
    for index, path in enumerate(paths):
        with wave.open(str(path), "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                raise RuntimeError(f"unexpected preview format: {path}")
            chunks.append(source.readframes(source.getnframes()))
        if index + 1 < len(paths):
            chunks.append(silence)
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"".join(chunks))


def main() -> None:
    PREVIEW.mkdir(parents=True, exist_ok=True)
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    results = []
    for source in sorted(RAW.glob("*")):
        if source.suffix.lower() not in {".mp3", ".wav", ".flac", ".m4a"}:
            continue
        destination = PREVIEW / f"{source.stem}.wav"
        convert(source, destination)
        make_analysis(destination, source.stem)
        before = loudnorm_report(source, PREPROCESS)
        after = loudnorm_report(destination, "anull")
        results.append({
            "id": source.stem,
            "raw": {
                "path": str(source.relative_to(ROOT)),
                "sha256": sha256(source),
                **probe(source),
                "band_loudness_lufs": float(before["input_i"]),
                "band_true_peak_dbtp": float(before["input_tp"]),
            },
            "device_preview": {
                "path": str(destination.relative_to(ROOT)),
                "sha256": sha256(destination),
                **probe(destination),
                "loudness_lufs": float(after["input_i"]),
                "true_peak_dbtp": float(after["input_tp"]),
            },
        })
    report = {
        "version": 1,
        "status": "audition only; not part of the canonical firmware audio pack",
        "processing": {
            "target_loudness_lufs": TARGET_LUFS,
            "target_true_peak_dbtp": TARGET_TRUE_PEAK,
            "highpass_hz": 300,
            "lowpass_hz": 5000,
            "sample_rate": 16000,
            "channels": 1,
            "codec": "PCM signed 16-bit little-endian",
            "duration_seconds": TARGET_DURATION_SECONDS,
        },
        "asset_count": len(results),
        "assets": results,
    }
    by_id = {entry["id"]: PREVIEW / Path(entry["device_preview"]["path"]).name
             for entry in results}
    species_order = [
        "moon-jelly", "reef-shark", "giant-octopus", "seahorse",
        "glass-squid", "anglerfish", "sea-angel", "gulper-eel",
    ]
    species_paths = [
        by_id[f"{name}__elevenlabs-sound-effects-v2"] for name in species_order
    ]
    comparison_order = [
        "shared-bubbles__elevenlabs-sound-effects-v2",
        "shared-bubbles__mmaudio-v2-text-to-audio",
        "shared-bubbles__sonilo-v1-1-sound-effects",
    ]
    build_reel(species_paths, SPECIES_REEL, 0.5)
    build_reel([by_id[name] for name in comparison_order], COMPARISON_REEL, 0.75)
    report["audition_reels"] = {
        "species": {
            "path": SPECIES_REEL.name,
            "order": species_order,
            "gap_seconds": 0.5,
            "sha256": sha256(SPECIES_REEL),
            **probe(SPECIES_REEL),
        },
        "model_comparison": {
            "path": COMPARISON_REEL.name,
            "order": comparison_order,
            "gap_seconds": 0.75,
            "sha256": sha256(COMPARISON_REEL),
            **probe(COMPARISON_REEL),
        },
    }
    MANIFEST.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Prepared {len(results)} audition assets")
    print(f"Wrote {MANIFEST}")


if __name__ == "__main__":
    main()
