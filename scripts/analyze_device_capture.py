#!/usr/bin/env python3
"""Identify packed source cues heard by the MacBook microphone."""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np
from scipy import signal


def read_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise RuntimeError(f"expected mono signed-16 PCM: {path}")
        rate = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    audio = samples.astype(np.float64)
    audio -= np.mean(audio)
    return audio, rate


def normalized_match(capture: np.ndarray, reference: np.ndarray) -> tuple[float, int]:
    if len(reference) > len(capture):
        return 0.0, 0
    reference = reference - np.mean(reference)
    reference_energy = np.sum(reference * reference)
    if reference_energy == 0:
        return 0.0, 0
    correlation = signal.fftconvolve(capture, reference[::-1], mode="valid")
    cumulative = np.concatenate(([0.0], np.cumsum(capture * capture)))
    window_energy = cumulative[len(reference):] - cumulative[:-len(reference)]
    scores = np.abs(correlation) / np.sqrt(np.maximum(window_energy * reference_energy, 1e-12))
    index = int(np.argmax(scores))
    return float(scores[index]), index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--references", type=Path,
                        default=Path("audio/generated/device-pcm"))
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    capture, capture_rate = read_mono(args.capture)
    target_rate = 16000
    if capture_rate != target_rate:
        divisor = np.gcd(capture_rate, target_rate)
        capture = signal.resample_poly(
            capture, target_rate // divisor, capture_rate // divisor)
    capture = signal.sosfilt(
        signal.butter(4, [100, 7000], btype="bandpass", fs=target_rate, output="sos"),
        capture)

    matches: list[tuple[float, float, str]] = []
    for path in sorted(args.references.glob("*.wav")):
        reference, rate = read_mono(path)
        if rate != target_rate:
            raise RuntimeError(f"unexpected reference rate {rate}: {path}")
        reference = signal.sosfilt(
            signal.butter(4, [100, 7000], btype="bandpass", fs=target_rate, output="sos"),
            reference)
        score, index = normalized_match(capture, reference)
        matches.append((score, index / target_rate, path.stem))

    for score, seconds, asset_id in sorted(matches, reverse=True)[:args.top]:
        print(f"{score:0.4f}  {seconds:7.3f}s  {asset_id}")


if __name__ == "__main__":
    main()
