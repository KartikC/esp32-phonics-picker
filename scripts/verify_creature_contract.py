#!/usr/bin/env python3
"""Verify the generated creature count/frame contract against its manifest."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CreatureContract:
    creature_ids: tuple[str, ...]
    frame_count: int
    palette_ids: tuple[str, ...]

    @property
    def creature_count(self) -> int:
        return len(self.creature_ids)

    @property
    def total_frames(self) -> int:
        return self.creature_count * self.frame_count


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"required creature contract file is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"creature contract file is not a JSON object: {path}")
    return value


def load_creature_contract(root: Path = ROOT) -> CreatureContract:
    manifest_path = root / "creatures/variation/variation_manifest.json"
    report_path = root / "creatures/variation/generated/variation_report.json"
    manifest = _load_json(manifest_path)
    report = _load_json(report_path)

    if manifest.get("schema_version") != 1:
        raise RuntimeError("creature variation manifest schema is unsupported")
    if report.get("schema_version") != 1 or report.get("status") != "passed":
        raise RuntimeError("creature variation report is not passing")
    if report.get("manifest_sha256") != _sha256_file(manifest_path):
        raise RuntimeError("creature variation report does not match its manifest")

    animals = manifest.get("animals")
    frame_count = manifest.get("frame_count")
    palettes = manifest.get("palettes")
    if not isinstance(animals, list) or not animals:
        raise RuntimeError("creature variation manifest has no animals")
    if not isinstance(frame_count, int) or frame_count <= 0:
        raise RuntimeError("creature variation manifest has an invalid frame count")
    if not isinstance(palettes, list) or not palettes:
        raise RuntimeError("creature variation manifest has no palettes")
    if any(not isinstance(asset, dict) for asset in animals):
        raise RuntimeError("creature variation manifest has an invalid animal entry")
    if any(not isinstance(palette, dict) for palette in palettes):
        raise RuntimeError("creature variation manifest has an invalid palette entry")

    creature_ids = tuple(asset.get("id") for asset in animals)
    palette_ids = tuple(palette.get("id") for palette in palettes)
    if any(not isinstance(value, str) or not value for value in creature_ids):
        raise RuntimeError("creature variation manifest has an invalid animal id")
    if len(set(creature_ids)) != len(creature_ids):
        raise RuntimeError("creature variation manifest has duplicate animal ids")
    if any(not isinstance(value, str) or not value for value in palette_ids):
        raise RuntimeError("creature variation manifest has an invalid palette id")
    if len(set(palette_ids)) != len(palette_ids):
        raise RuntimeError("creature variation manifest has duplicate palette ids")

    report_assets = report.get("assets")
    if not isinstance(report_assets, list):
        raise RuntimeError("creature variation report has no asset list")
    if any(not isinstance(asset, dict) for asset in report_assets):
        raise RuntimeError("creature variation report has an invalid asset entry")
    report_ids = tuple(asset.get("id") for asset in report_assets)
    if report_ids != creature_ids:
        raise RuntimeError(
            "creature variation report animal order differs from its manifest"
        )
    if report.get("palette_ids") != list(palette_ids):
        raise RuntimeError(
            "creature variation report palette order differs from its manifest"
        )
    if report.get("palette_count") != len(palette_ids):
        raise RuntimeError("creature variation report palette count is inconsistent")
    semantic_roles = manifest.get("semantic_roles")
    if not isinstance(semantic_roles, list) or report.get(
        "semantic_role_count"
    ) != len(semantic_roles):
        raise RuntimeError("creature variation semantic role count is inconsistent")

    for manifest_asset, asset in zip(animals, report_assets):
        expected_metadata = {
            "logical_size": manifest_asset.get("logical_size"),
            "base_rarity": manifest_asset.get("base_rarity"),
            "animation": manifest_asset.get("animation"),
            "automatic_palette_indices": manifest_asset.get(
                "automatic_palette_indices", [0, 1, 2, 4, 5]
            ),
            "celebration_sparkles": manifest_asset.get(
                "celebration_sparkles", True
            ),
        }
        for key, expected in expected_metadata.items():
            if asset.get(key) != expected:
                raise RuntimeError(
                    f"creature report {key} differs for {asset.get('id')}"
                )
        authored_definition = manifest_asset.get("authored_animation")
        authored_report = asset.get("authored_animation")
        if authored_definition:
            if not isinstance(authored_report, dict):
                raise RuntimeError(
                    f"creature authored animation is missing: {asset.get('id')}"
                )
            if (
                authored_report.get("manifest") !=
                    authored_definition.get("manifest") or
                authored_report.get("report") !=
                    authored_definition.get("report")
            ):
                raise RuntimeError(
                    f"creature authored animation provenance differs: {asset.get('id')}"
                )
            for path_key, hash_key in (
                ("manifest", "manifest_sha256"),
                ("report", "report_sha256"),
                ("reviewed_spritesheet", "reviewed_spritesheet_sha256"),
            ):
                path = root / authored_report[path_key]
                if not path.is_file() or _sha256_file(path) != authored_report[hash_key]:
                    raise RuntimeError(
                        f"creature authored animation artifact differs: {asset.get('id')}"
                    )
        elif authored_report is not None:
            raise RuntimeError(
                f"unexpected creature authored animation: {asset.get('id')}"
            )
        animation_audit = asset.get("animation_audit")
        if not isinstance(animation_audit, dict) or not animation_audit or not all(
            animation_audit.values()
        ):
            raise RuntimeError(
                f"creature animation gate failed: {asset.get('id', 'unknown')}"
            )
        component_counts = asset.get("connected_component_count")
        if not isinstance(component_counts, list) or len(
            component_counts
        ) != frame_count or any(
            not isinstance(count, int) or count <= 0
            for count in component_counts
        ):
            raise RuntimeError(
                f"creature component audit is invalid: {asset.get('id', 'unknown')}"
            )
        frame_checks = asset.get("frame_checks")
        if not isinstance(frame_checks, list) or len(frame_checks) != frame_count:
            raise RuntimeError(
                f"creature frame count differs for {asset.get('id', 'unknown')}"
            )
        if not all(
            isinstance(checks, dict) and checks and all(checks.values())
            for checks in frame_checks
        ):
            raise RuntimeError(
                f"creature frame gate failed: {asset.get('id', 'unknown')}"
            )

    return CreatureContract(creature_ids, frame_count, palette_ids)


def main() -> None:
    contract = load_creature_contract()
    print(
        "Creature contract verified: "
        f"{contract.creature_count} creatures x {contract.frame_count} frames "
        f"= {contract.total_frames} generated frames; "
        f"{len(contract.palette_ids)} palettes"
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        print(f"creature contract verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
