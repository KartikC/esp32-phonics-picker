#!/usr/bin/env python3
"""Generate offline cue candidates from the approved Cowboy anchor.

This script never plays audio. It uses one isolated utterance at a time, the
approved Apple/Car/Dog anchor, Qwen3-TTS Base 8-bit, and the approved fixed
Cowboy seed. Set COWBOY_ANCHOR to the reviewed reference WAV before running it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import mlx.core as mx
import numpy as np
from mlx_audio.tts.utils import load_model
from scipy.io import wavfile


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "audio/cowboy-cues.json"
OUTPUT = ROOT / "audio/generated/cowboy-cues/raw"
ANCHOR_SETTING = os.environ.get("COWBOY_ANCHOR")
ANCHOR = Path(ANCHOR_SETTING).expanduser() if ANCHOR_SETTING else None
ANCHOR_SHA256 = "3e9134770d92fb179601a32a5384c1a52715628faf455a585d163d13250c60d3"
ANCHOR_TEXT = "Apple. Car. Dog."
MODEL_ID = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"
SEED = 970011


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_one(results, destination: Path) -> dict[str, float | int]:
    segments = list(results)
    if len(segments) != 1:
        raise RuntimeError(f"Expected one segment for {destination.name}")
    result = segments[0]
    waveform = np.asarray(result.audio, dtype=np.float32).reshape(-1)
    if not waveform.size or float(np.max(np.abs(waveform))) < 0.005:
        raise RuntimeError(f"Invalid waveform for {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(destination, result.sample_rate, waveform)
    return {
        "sample_rate": int(result.sample_rate),
        "duration_seconds": round(waveform.size / result.sample_rate, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cue", action="append", help="Generate only this cue ID")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if ANCHOR is None or not ANCHOR.is_file():
        raise SystemExit("Set COWBOY_ANCHOR to the approved Cowboy reference WAV")
    if sha256(ANCHOR) != ANCHOR_SHA256:
        raise SystemExit("Cowboy anchor hash does not match the approved artifact")

    corpus = json.loads(CORPUS.read_text())
    cues: dict[str, str] = corpus["cues"]
    requested = set(args.cue or cues)
    unknown = requested.difference(cues)
    if unknown:
        raise SystemExit(f"Unknown cue IDs: {', '.join(sorted(unknown))}")
    pending = [
        (cue_id, text)
        for cue_id, text in cues.items()
        if cue_id in requested and (args.force or not (OUTPUT / f"{cue_id}.wav").exists())
    ]
    if not pending:
        print("All requested Cowboy cues already exist.")
        return

    print(f"Loading {MODEL_ID}", flush=True)
    model = load_model(MODEL_ID)
    report = {
        "model": MODEL_ID,
        "anchor": str(ANCHOR),
        "anchor_sha256": ANCHOR_SHA256,
        "anchor_transcript": ANCHOR_TEXT,
        "seed": SEED,
        "playback_performed": False,
        "cues": {},
    }
    for index, (cue_id, text) in enumerate(pending, 1):
        mx.random.seed(SEED)
        destination = OUTPUT / f"{cue_id}.wav"
        metrics = save_one(
            model.generate(
                text=text,
                ref_audio=str(ANCHOR),
                ref_text=ANCHOR_TEXT,
                lang_code="English",
                temperature=0.65,
                top_k=40,
                top_p=0.9,
                repetition_penalty=1.5,
                max_tokens=128,
            ),
            destination,
        )
        report["cues"][cue_id] = {"text": text, "file": destination.name, **metrics}
        print(f"[{index:02d}/{len(pending):02d}] {cue_id}: {metrics['duration_seconds']:.3f}s", flush=True)
        mx.clear_cache()

    report_path = OUTPUT.parent / "generation-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
