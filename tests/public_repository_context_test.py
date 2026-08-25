#!/usr/bin/env python3
"""Keep public repository prose self-contained and rarity docs discoverable."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()

FORBIDDEN = (
    (re.compile(r"dream\s+duel", re.IGNORECASE), "unrelated private project name"),
    (re.compile(r"/Users/[^/\s]+/"), "local absolute path"),
    (re.compile(r"/dev/cu\.usbmodem\d+", re.IGNORECASE), "ephemeral serial path"),
    (re.compile(r"user[- ]selected", re.IGNORECASE), "insider selection wording"),
    (re.compile(r"user[- ]confirmed", re.IGNORECASE), "insider verification wording"),
    (re.compile(r"owner[- ]verified", re.IGNORECASE), "personal account wording"),
    (re.compile(r"same previously approved", re.IGNORECASE), "insider history wording"),
    (re.compile(r"the user accepted", re.IGNORECASE), "insider review wording"),
)


tracked = subprocess.run(
    ["git", "ls-files", "-z"],
    cwd=ROOT,
    check=True,
    capture_output=True,
).stdout.split(b"\0")

violations: list[str] = []
for raw_path in tracked:
    if not raw_path:
        continue
    relative = raw_path.decode("utf-8")
    path = ROOT / relative
    if path.resolve() == SELF or not path.is_file():
        continue
    data = path.read_bytes()
    if b"\0" in data:
        continue
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        continue
    for pattern, label in FORBIDDEN:
        match = pattern.search(text)
        if match:
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{relative}:{line}: {label}")

if violations:
    raise AssertionError("public-context violations:\n" + "\n".join(violations))

readme = (ROOT / "README.md").read_text()
for required in (
    "## Creature rewards and rarity",
    "22.83% (`200/876`)",
    "1/64 (1.5625%)",
    "12 | Guaranteed",
    "18th correct answer",
    "rare visual-treatment roll",
):
    if required not in readme:
        raise AssertionError(f"README rarity contract is missing: {required!r}")

print("public_repository_context_test passed")
