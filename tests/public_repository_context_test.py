#!/usr/bin/env python3
"""Keep public prose self-contained and agent development routes usable."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()

FORBIDDEN = (
    (re.compile(r"/Users/[^/\s]+/"), "local absolute path"),
    (re.compile(r"/dev/cu\.usbmodem\d+", re.IGNORECASE), "ephemeral serial path"),
    (re.compile(r"user[- ]selected", re.IGNORECASE), "insider selection wording"),
    (re.compile(r"user[- ]confirmed", re.IGNORECASE), "insider verification wording"),
    (re.compile(r"owner[- ]verified", re.IGNORECASE), "personal account wording"),
    (re.compile(r"same previously approved", re.IGNORECASE), "insider history wording"),
    (re.compile(r"the user accepted", re.IGNORECASE), "insider review wording"),
)

AGENT_GUIDES = (
    Path(".agents/skills/develop-waveshare-s3-amoled-v2/SKILL.md"),
    Path("docs/DEVELOPMENT_SPEED_STRATEGY.md"),
    Path("docs/WAVESHARE_S3_AMOLED_V2_DEVELOPMENT.md"),
)


tracked = subprocess.run(
    ["git", "ls-files", "-z"],
    cwd=ROOT,
    check=True,
    capture_output=True,
).stdout.split(b"\0")

public_paths = {
    raw_path.decode("utf-8")
    for raw_path in tracked
    if raw_path
}
public_paths.update(path.as_posix() for path in AGENT_GUIDES)

violations: list[str] = []
for relative in sorted(public_paths):
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

for relative in AGENT_GUIDES:
    path = ROOT / relative
    if not path.is_file():
        raise AssertionError(f"public agent guide is missing: {relative}")

skill = (ROOT / AGENT_GUIDES[0]).read_text()
if not re.match(
    r"\A---\nname: develop-waveshare-s3-amoled-v2\n"
    r"description: [^\n]+\n---\n",
    skill,
):
    raise AssertionError("public board skill frontmatter is missing or invalid")

for relative in AGENT_GUIDES:
    path = ROOT / relative
    text = path.read_text()
    for destination in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        if "://" in destination or destination.startswith("#"):
            continue
        target = destination.split("#", 1)[0]
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError as error:
            raise AssertionError(
                f"public agent guide link escapes repository: {relative} -> {target}"
            ) from error
        if not resolved.exists():
            raise AssertionError(
                f"public agent guide link is missing: {relative} -> {target}"
            )

readme = (ROOT / "README.md").read_text()
agents = (ROOT / "AGENTS.md").read_text()
for relative in AGENT_GUIDES:
    target = relative.as_posix()
    if target not in readme and target not in agents:
        raise AssertionError(f"public agent guide is not discoverable: {target}")

for required in (
    "## Creature rewards and rarity",
    "22.18% (`20720/93414`)",
    "1/50 (2.000%)",
    "10 | Guaranteed",
    "14th correct answer",
    "rare visual-treatment roll",
):
    if required not in readme:
        raise AssertionError(f"README rarity contract is missing: {required!r}")

print("public_repository_context_test passed")
