#!/usr/bin/env python3
"""Remove host-derived ELF metadata from an ESP32 application image.

Arduino-ESP32 asks esptool to copy the complete ELF file SHA-256 into the app
descriptor at image offset 0xb0. Debug-only ELF contents differ across host
operating systems even when every loadable byte is identical. This script
zeros that informational field, then recomputes the ESP image checksum and
validation digest without changing any executable or asset bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import tempfile
from pathlib import Path


IMAGE_HEADER_BYTES = 24
SEGMENT_HEADER = struct.Struct("<II")
ELF_SHA256_OFFSET = 0xB0
ELF_SHA256_BYTES = 32
CHECKSUM_SEED = 0xEF


def fail(message: str) -> None:
    raise RuntimeError(message)


def canonicalize(path: Path) -> None:
    image = bytearray(path.read_bytes())
    if len(image) < IMAGE_HEADER_BYTES + 33 or image[0] != 0xE9:
        fail("not an ESP application image")

    digest_offset = len(image) - 32
    checksum_offset = digest_offset - 1
    if image[digest_offset:] != hashlib.sha256(image[:digest_offset]).digest():
        fail("input image validation digest is invalid")

    segment_ranges: list[tuple[int, int]] = []
    cursor = IMAGE_HEADER_BYTES
    for _ in range(image[1]):
        if cursor + SEGMENT_HEADER.size > checksum_offset:
            fail("truncated ESP segment header")
        _, length = SEGMENT_HEADER.unpack_from(image, cursor)
        start = cursor + SEGMENT_HEADER.size
        end = start + length
        if end > checksum_offset:
            fail("truncated ESP segment data")
        segment_ranges.append((start, end))
        cursor = end

    if checksum_offset % 16 != 15 or any(image[cursor:checksum_offset]):
        fail("unexpected ESP image padding or checksum position")
    if not any(
        start <= ELF_SHA256_OFFSET
        and ELF_SHA256_OFFSET + ELF_SHA256_BYTES <= end
        for start, end in segment_ranges
    ):
        fail("ELF SHA-256 field is outside the loadable segments")

    checksum = CHECKSUM_SEED
    for start, end in segment_ranges:
        for value in image[start:end]:
            checksum ^= value
    if image[checksum_offset] != checksum:
        fail("input ESP image checksum is invalid")

    image[ELF_SHA256_OFFSET : ELF_SHA256_OFFSET + ELF_SHA256_BYTES] = b"\0" * 32
    checksum = CHECKSUM_SEED
    for start, end in segment_ranges:
        for value in image[start:end]:
            checksum ^= value
    image[checksum_offset] = checksum
    image[digest_offset:] = hashlib.sha256(image[:digest_offset]).digest()

    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(image)
        output.flush()
        os.fsync(output.fileno())
    temporary.chmod(path.stat().st_mode)
    temporary.replace(path)
    print(f"Canonicalized host-derived ELF metadata: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    canonicalize(args.image.resolve())


if __name__ == "__main__":
    main()
