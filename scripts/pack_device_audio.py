#!/usr/bin/env python3
"""Pack reviewed 16 kHz mono WAV payloads into the board's raw audio partition."""

from __future__ import annotations

import hashlib
import json
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "audio/generated/device-pcm"
MANIFEST = ROOT / "audio/generated/device-audio-manifest.json"
PACK = ROOT / "audio/generated/phonics-audio-pack.bin"
PACK_MANIFEST = ROOT / "audio/generated/phonics-audio-pack-manifest.json"
INDEX = ROOT / "firmware/PhonicsGame/AudioAssetIndex.h"
HEADER = struct.Struct("<8sIIII8s")


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    assets = manifest["assets"]
    payloads: list[tuple[str, bytes]] = []
    for asset in assets:
        path = SOURCE / f"{asset['id']}.wav"
        with wave.open(str(path), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
                raise RuntimeError(f"unsupported PCM format: {path}")
            pcm = wav.readframes(wav.getnframes())
        if not pcm or len(pcm) % 2:
            raise RuntimeError(f"invalid PCM payload: {path}")
        payloads.append((asset["id"], pcm))

    body_size = sum(len(data) for _, data in payloads)
    blob = bytearray(HEADER.pack(b"PHONICS1", 1, len(payloads), 16000, body_size, b"\0" * 8))
    entries = []
    for asset_id, data in payloads:
        entries.append((asset_id, len(blob), len(data)))
        blob.extend(data)
    PACK.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()

    lines = [
        "#pragma once",
        "#include <stdint.h>",
        "#include <string.h>",
        "",
        "namespace phonics_game {",
        "struct PackedAudioAsset { const char* id; uint32_t offset; uint32_t length; };",
        f'constexpr const char* kAudioPackSha256 = "{digest}";',
        "constexpr uint8_t kAudioPackSha256Bytes[32] = {" +
        ", ".join(f"0x{value:02x}" for value in bytes.fromhex(digest)) + "};",
        f"constexpr uint32_t kAudioPackBytes = {len(blob)}u;",
        f"constexpr uint16_t kPackedAudioAssetCount = {len(entries)};",
        "constexpr PackedAudioAsset kPackedAudioAssets[] = {",
    ]
    lines += [f'  {{"{name}", {offset}u, {length}u}},' for name, offset, length in entries]
    lines += [
        "};",
        "inline const PackedAudioAsset* findPackedAudioAsset(const char* id) {",
        "  for (const auto& asset : kPackedAudioAssets) {",
        "    if (strcmp(asset.id, id) == 0) return &asset;",
        "  }",
        "  return nullptr;",
        "}",
        "}  // namespace phonics_game",
        "",
    ]
    INDEX.write_text("\n".join(lines))
    PACK_MANIFEST.write_text(json.dumps({
        "version": 1,
        "magic": "PHONICS1",
        "sample_rate": 16000,
        "format": "PCM signed 16-bit little-endian, mono",
        "asset_count": len(entries),
        "bytes": len(blob),
        "sha256": digest,
        "flash_partition": {"label": "ffat", "offset": "0x610000", "size": "0x9E0000"},
        "assets": [{"id": name, "offset": offset, "length": length}
                   for name, offset, length in entries],
    }, indent=2) + "\n")
    print(f"Packed {len(entries)} assets, {len(blob)} bytes, sha256={digest}")
    print(PACK)


if __name__ == "__main__":
    main()
