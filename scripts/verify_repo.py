#!/usr/bin/env python3
"""Verify all checked-in inputs required for an exact public deployment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_HEADER = struct.Struct("<8sIIII8s")
EXPECTED_VENDOR_COMMIT = "7ab8f957e22ea1ab811256359f4eddcaaf49ee91"
EXPECTED_PACK_SHA256 = "563943402470eada0150e74720086d33ef9921d8b07e58e14247f18e9175ea72"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(message)


def require(path: Path) -> None:
    if not path.is_file():
        fail(f"required file is missing: {path.relative_to(ROOT)}")


def verify_vendor() -> None:
    probe = ROOT / (
        "vendor/waveshare-esp32-s3-touch-amoled-1.8/examples/arduino-v2/"
        "libraries/Adafruit_BusIO/library.properties"
    )
    require(probe)
    git_dir = ROOT / ".git"
    vendor = ROOT / "vendor/waveshare-esp32-s3-touch-amoled-1.8"
    if git_dir.exists() and ((vendor / ".git").exists()):
        completed = subprocess.run(
            ["git", "-C", str(vendor), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        actual = completed.stdout.strip()
        if actual != EXPECTED_VENDOR_COMMIT:
            fail(f"Waveshare submodule is {actual}, expected {EXPECTED_VENDOR_COMMIT}")


def verify_build_contract() -> None:
    values: dict[str, str] = {}
    for line in (ROOT / "config/toolchain.env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    manifest = json.loads((ROOT / "firmware/BUILD_MANIFEST.json").read_text())
    expected_metadata = {
        "arduino_cli": values.get("ARDUINO_CLI_VERSION"),
        "arduino_esp32": values.get("ARDUINO_ESP32_VERSION"),
        "waveshare_commit": values.get("WAVESHARE_COMMIT"),
        "source_date_epoch": int(values.get("BUILD_SOURCE_DATE_EPOCH", "0")),
        "board_fqbn": values.get("BOARD_FQBN"),
    }
    for key, expected in expected_metadata.items():
        if manifest.get(key) != expected:
            fail(f"BUILD_MANIFEST.json {key} differs from config/toolchain.env")
    expected_offsets = {
        "PhonicsGame.ino.bootloader.bin": "0x0",
        "PhonicsGame.ino.partitions.bin": "0x8000",
        "boot_app0.bin": "0xe000",
        "PhonicsGame.ino.bin": "0x10000",
        "phonics-audio-pack.bin": "0x610000",
    }
    actual_offsets = {artifact["name"]: artifact["offset"] for artifact in manifest["artifacts"]}
    if actual_offsets != expected_offsets:
        fail("BUILD_MANIFEST.json artifact names or flash offsets are invalid")


def verify_audio() -> None:
    device_manifest_path = ROOT / "audio/generated/device-audio-manifest.json"
    pack_manifest_path = ROOT / "audio/generated/phonics-audio-pack-manifest.json"
    pack_path = ROOT / "audio/generated/phonics-audio-pack.bin"
    index_path = ROOT / "firmware/PhonicsGame/AudioAssetIndex.h"
    for path in (device_manifest_path, pack_manifest_path, pack_path, index_path):
        require(path)

    device_manifest = json.loads(device_manifest_path.read_text())
    pack_manifest = json.loads(pack_manifest_path.read_text())
    assets = device_manifest["assets"]
    packed_assets = pack_manifest["assets"]
    if len(assets) != 42 or device_manifest["asset_count"] != 42:
        fail("device manifest must contain exactly 42 audio assets")
    if len(packed_assets) != 42 or pack_manifest["asset_count"] != 42:
        fail("pack manifest must contain exactly 42 audio assets")

    pack = pack_path.read_bytes()
    pack_sha = sha256_bytes(pack)
    if pack_sha != EXPECTED_PACK_SHA256 or pack_manifest["sha256"] != pack_sha:
        fail(f"audio pack SHA-256 mismatch: {pack_sha}")
    if pack_manifest["bytes"] != len(pack):
        fail("audio pack byte count does not match its manifest")
    if pack_manifest.get("flash_partition") != {
        "label": "ffat", "offset": "0x610000", "size": "0x9E0000"
    }:
        fail("audio pack flash partition metadata is invalid")

    magic, version, count, sample_rate, payload_bytes, reserved = PACK_HEADER.unpack_from(pack)
    if (magic, version, count, sample_rate, reserved) != (
        b"PHONICS1", 1, 42, 16000, b"\0" * 8
    ):
        fail("audio pack header is invalid")
    if payload_bytes != len(pack) - PACK_HEADER.size:
        fail("audio pack payload length is invalid")

    by_id = {asset["id"]: asset for asset in assets}
    expected_offset = PACK_HEADER.size
    for entry in packed_assets:
        asset_id = entry["id"]
        if asset_id not in by_id:
            fail(f"packed asset is absent from device manifest: {asset_id}")
        wav_path = ROOT / "audio/generated/device-pcm" / f"{asset_id}.wav"
        require(wav_path)
        wav_bytes = wav_path.read_bytes()
        asset = by_id[asset_id]
        if len(wav_bytes) != asset["bytes"]:
            fail(f"WAV byte count mismatch: {asset_id}")
        if sha256_bytes(wav_bytes) != asset["output_sha256"]:
            fail(f"WAV SHA-256 mismatch: {asset_id}")
        with wave.open(str(wav_path), "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                fail(f"unsupported WAV format: {asset_id}")
            pcm = source.readframes(source.getnframes())
        if entry["offset"] != expected_offset or entry["length"] != len(pcm):
            fail(f"packed index mismatch: {asset_id}")
        if pack[entry["offset"] : entry["offset"] + entry["length"]] != pcm:
            fail(f"packed PCM differs from accepted WAV: {asset_id}")
        expected_offset += len(pcm)
    if expected_offset != len(pack):
        fail("audio pack contains unindexed trailing bytes")

    index = index_path.read_text()
    if EXPECTED_PACK_SHA256 not in index or f"kAudioPackBytes = {len(pack)}u" not in index:
        fail("firmware audio index does not match the checked-in pack")
    for entry in packed_assets:
        marker = f'{{"{entry["id"]}", {entry["offset"]}u, {entry["length"]}u}}'
        if marker not in index:
            fail(f"firmware audio index is missing or differs for {entry['id']}")


def verify_build(build_dir: Path) -> None:
    required = [
        "PhonicsGame.ino.bin",
        "PhonicsGame.ino.bootloader.bin",
        "PhonicsGame.ino.partitions.bin",
        "boot_app0.bin",
        "partitions.csv",
    ]
    for name in required:
        path = build_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            fail(f"build artifact is missing or empty: {path}")

    partitions: dict[str, tuple[int, int]] = {}
    with (build_dir / "partitions.csv").open(newline="") as source:
        for row in csv.reader(line for line in source if not line.lstrip().startswith("#")):
            if not row or not row[0].strip():
                continue
            name = row[0].strip()
            partitions[name] = (int(row[3].strip(), 0), int(row[4].strip(), 0))
    expected = {
        "app0": (0x10000, 0x300000),
        "app1": (0x310000, 0x300000),
        "ffat": (0x610000, 0x9E0000),
        "coredump": (0xFF0000, 0x10000),
    }
    for name, value in expected.items():
        if partitions.get(name) != value:
            fail(f"partition {name} is {partitions.get(name)}, expected {value}")
    if (build_dir / "PhonicsGame.ino.bin").stat().st_size > expected["app0"][1]:
        fail("application image exceeds its partition")
    if (ROOT / "audio/generated/phonics-audio-pack.bin").stat().st_size > expected["ffat"][1]:
        fail("audio pack exceeds its partition")

    build_manifest = json.loads((ROOT / "firmware/BUILD_MANIFEST.json").read_text())
    for artifact in build_manifest["artifacts"]:
        if artifact["name"] == "phonics-audio-pack.bin":
            path = ROOT / "audio/generated/phonics-audio-pack.bin"
        else:
            path = build_dir / artifact["name"]
        data = path.read_bytes()
        if len(data) != artifact["bytes"]:
            fail(f"artifact byte count differs from BUILD_MANIFEST.json: {path.name}")
        actual_sha256 = sha256_bytes(data)
        if actual_sha256 != artifact["sha256"]:
            fail(
                f"artifact SHA-256 differs from BUILD_MANIFEST.json: {path.name}; "
                f"expected {artifact['sha256']}, got {actual_sha256}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path)
    args = parser.parse_args()
    for relative in (
        "firmware/PhonicsGame/PhonicsGame.ino",
        "firmware/PhonicsGame/fonts/NunitoBlack112.h",
        "firmware/PhonicsGame/fonts/NunitoBold28.h",
        "config/toolchain.env",
        "firmware/BUILD_MANIFEST.json",
        "PRODUCT_SPEC.md",
    ):
        require(ROOT / relative)
    verify_vendor()
    verify_build_contract()
    verify_audio()
    if args.build_dir:
        verify_build(args.build_dir.resolve())
    print("Repository payload verified")


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
