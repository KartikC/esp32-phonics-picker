#!/usr/bin/env python3
"""Prepare the second Venice SFX iteration with the first pass as references."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EXPERIMENT_ROOT = ROOT.parent
RAW = ROOT / "raw"
PREVIEW = ROOT / "device-preview"
ANALYSIS = ROOT / "analysis"
RESULTS = ROOT / "results.json"


def load_processor():
    path = EXPERIMENT_ROOT / "process_experiment.py"
    spec = importlib.util.spec_from_file_location("venice_sfx_processor", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    processor = load_processor()
    PREVIEW.mkdir(parents=True, exist_ok=True)
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    processor.ANALYSIS = ANALYSIS

    assets = []
    by_id: dict[str, Path] = {}
    for source in sorted(RAW.glob("*.mp3")):
        destination = PREVIEW / f"{source.stem}.wav"
        processor.convert(source, destination)
        processor.make_analysis(destination, source.stem)
        before = processor.loudnorm_report(source, processor.PREPROCESS)
        after = processor.loudnorm_report(destination, "anull")
        by_id[source.stem] = destination
        assets.append({
            "id": source.stem,
            "raw": {
                "path": str(source.relative_to(ROOT)),
                "sha256": processor.sha256(source),
                **processor.probe(source),
                "band_loudness_lufs": float(before["input_i"]),
                "band_true_peak_dbtp": float(before["input_tp"]),
            },
            "device_preview": {
                "path": str(destination.relative_to(ROOT)),
                "sha256": processor.sha256(destination),
                **processor.probe(destination),
                "loudness_lufs": float(after["input_i"]),
                "true_peak_dbtp": float(after["input_tp"]),
            },
        })

    reference_sources = {
        "selected-bubbles-reference": (
            EXPERIMENT_ROOT / "device-preview" /
            "shared-bubbles__elevenlabs-sound-effects-v2.wav"
        ),
        "original-shark-reference": (
            EXPERIMENT_ROOT / "device-preview" /
            "reef-shark__elevenlabs-sound-effects-v2.wav"
        ),
    }
    references = {}
    for reference_id, source in reference_sources.items():
        destination = PREVIEW / f"{reference_id}.wav"
        shutil.copyfile(source, destination)
        references[reference_id] = destination

    bubble_order = [
        "selected-bubbles-reference",
        "bubbles-even__elevenlabs-sound-effects-v2",
        "bubbles-large-last__elevenlabs-sound-effects-v2",
        "bubbles-cascade__elevenlabs-sound-effects-v2",
    ]
    shark_order = [
        "original-shark-reference",
        "shark-pressure-pulse__elevenlabs-sound-effects-v2",
        "shark-glide-chomp__elevenlabs-sound-effects-v2",
        "shark-suction-wake__elevenlabs-sound-effects-v2",
    ]
    all_previews = {**by_id, **references}
    bubble_reel = ROOT / "bubble-variants-reel.wav"
    shark_reel = ROOT / "shark-chomp-variants-reel.wav"
    processor.build_reel([all_previews[item] for item in bubble_order], bubble_reel, 0.5)
    processor.build_reel([all_previews[item] for item in shark_order], shark_reel, 0.5)

    report = {
        "version": 1,
        "status": "audition only; not part of the canonical firmware audio pack",
        "processing": {
            "target_loudness_lufs": processor.TARGET_LUFS,
            "target_true_peak_dbtp": processor.TARGET_TRUE_PEAK,
            "highpass_hz": 300,
            "lowpass_hz": 5000,
            "sample_rate": 16000,
            "channels": 1,
            "codec": "PCM signed 16-bit little-endian",
            "duration_seconds": 2.0,
        },
        "asset_count": len(assets),
        "assets": assets,
        "audition_reels": {
            "bubble_variants": {
                "path": bubble_reel.name,
                "order": bubble_order,
                "gap_seconds": 0.5,
                "sha256": processor.sha256(bubble_reel),
                **processor.probe(bubble_reel),
            },
            "shark_chomp_variants": {
                "path": shark_reel.name,
                "order": shark_order,
                "gap_seconds": 0.5,
                "sha256": processor.sha256(shark_reel),
                **processor.probe(shark_reel),
            },
        },
    }
    RESULTS.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Prepared {len(assets)} new iteration-two assets")
    print(f"Wrote {RESULTS}")


if __name__ == "__main__":
    main()
