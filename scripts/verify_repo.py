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

from verify_creature_contract import load_creature_contract
from verify_reward_audio_mix import build_report as build_reward_mix_report

ROOT = Path(__file__).resolve().parents[1]
PACK_HEADER = struct.Struct("<8sIIII8s")
EXPECTED_VENDOR_COMMIT = "7ab8f957e22ea1ab811256359f4eddcaaf49ee91"
EXPECTED_PACK_SHA256 = "262858b9569618ca7bb901ba27fc0fd9034eb2f9e11a82176cda8ace7db19ba0"
EXPECTED_STONE_SOURCE_SHA256 = "80bb7f65419280532000c5399e159334f607a9087b67dbf31adc53e62da9b0df"
EXPECTED_STONE_REVIEW_SHA256 = "c59d70620c5f4b5eaeaac0c7c1715cd261c2ffb71fa886b2854a5d8c640444d6"
EXPECTED_REPLAY_SOURCE_SHA256 = "33badbf1df0a9035a86e611eca44715dafbe1bf5c4b5390b0b20ea8d1f4dd97f"
EXPECTED_REPLAY_METADATA_SHA256 = "98cdbddb1fb07d9abc9588888cfee6cd9a8436c9ce7ab22f0f8aaf290a6d2833"
EXPECTED_REPLAY_PACKED_SHA256 = "580ea7cf5f1a563093ba1b8900754bee75372d800e3ec6399baca52d5c9e2569"
EXPECTED_REPLAY_HEADER_SHA256 = "dae8475ec4bcf33bf35be5df1da838d8ca09833a1d3afbbccc4967dc28684509"
EXPECTED_BREAK_TIMER_SOURCE_SHA256 = "a47483a3503dc8615ae95a0797677ac0a14cd2fcf938a2f19fdfa181632d0b83"
EXPECTED_BREAK_TIMER_METADATA_SHA256 = "18c75543bf65415507781a88a9502168350fa00bb2f20c4e5d82134120d4373b"
EXPECTED_BREAK_TIMER_PACKED_SHA256 = "844f5b4ed579267908656aa2ae817025307befd341f48216c03b1198f01b3dd7"
EXPECTED_BREAK_TIMER_HEADER_SHA256 = "0c6a6ece42d6d26461ee0df7f6572ba0d9b83331ff790e87eef4517e0ea0e66a"
EXPECTED_ATKINSON_SOURCE_SHA256 = "5a455d1cfa099b601ab70751bb9673e8fe1854dc4500c80e1a220d0d75e31745"
EXPECTED_ATKINSON_CONTACT_SHA256 = "f7581b20245bc02a4b27528c525dcdfee38697adee9fdff41d852b1e727ef795"
EXPECTED_AUDIO_COUNTS = {
    "phonics": 26,
    "speech": 16,
    "reward_bubble": 4,
    "reward_creature": 8,
    "reward_mix": 32,
}
EXPECTED_AUDIO_ASSET_COUNT = sum(EXPECTED_AUDIO_COUNTS.values())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


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
    if (len(assets) != EXPECTED_AUDIO_ASSET_COUNT or
            device_manifest["asset_count"] != EXPECTED_AUDIO_ASSET_COUNT):
        fail(f"device manifest must contain exactly {EXPECTED_AUDIO_ASSET_COUNT} audio assets")
    actual_counts = {
        kind: sum(asset.get("kind") == kind for asset in assets)
        for kind in EXPECTED_AUDIO_COUNTS
    }
    if actual_counts != EXPECTED_AUDIO_COUNTS:
        fail(f"device audio category counts are invalid: {actual_counts}")
    if (len(packed_assets) != EXPECTED_AUDIO_ASSET_COUNT or
            pack_manifest["asset_count"] != EXPECTED_AUDIO_ASSET_COUNT):
        fail(f"pack manifest must contain exactly {EXPECTED_AUDIO_ASSET_COUNT} audio assets")

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
        b"PHONICS1", 1, EXPECTED_AUDIO_ASSET_COUNT, 16000, b"\0" * 8
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

    mix_report_path = ROOT / "audio/generated/reward-audio-mix-report.json"
    require(mix_report_path)
    checked_mix_report = json.loads(mix_report_path.read_text())
    generated_mix_report = build_reward_mix_report()
    if checked_mix_report != generated_mix_report:
        fail("reward audio mix report differs from the accepted WAVs")
    if (checked_mix_report.get("status") != "passed" or
            checked_mix_report.get("combination_count") != 32 or
            checked_mix_report.get("runtime_layer_count") != 1 or
            checked_mix_report.get("byte_exact_composite_count") != 32 or
            checked_mix_report.get("unclamped_clipped_sample_count") != 0):
        fail("reward audio mix safety gate failed")


def verify_creature_assets() -> None:
    manifest_path = ROOT / "creatures/variation/variation_manifest.json"
    report_path = ROOT / "creatures/variation/generated/variation_report.json"
    require(manifest_path)
    require(report_path)
    contract = load_creature_contract(ROOT)
    report = json.loads(report_path.read_text())
    if report.get("status") != "passed" or report.get("schema_version") != 1:
        fail("creature variation report is not passing")
    builder = report.get("builder")
    if builder != "scripts/build_creature_variations.py":
        fail("creature variation report has an unexpected builder")
    builder_path = ROOT / builder
    require(builder_path)
    if sha256_file(builder_path) != report.get("builder_sha256"):
        fail("creature variation builder differs from its audited report")
    if sha256_file(manifest_path) != report.get("manifest_sha256"):
        fail("creature variation manifest differs from its audited report")
    if report.get("header") != "firmware/CreatureAssets/GeneratedCreatureVariations.h":
        fail("creature report does not point to the shared runtime header")

    hashed_outputs = (
        (report["header"], report["header_sha256"]),
        (report["palette_comparison"], report["palette_comparison_sha256"]),
        (
            report["animation_comparison"],
            report["animation_comparison_sha256"],
        ),
        (report["protection_proof"], report["protection_proof_sha256"]),
        (
            report["stage3_pattern_comparison"],
            report["stage3_pattern_comparison_sha256"],
        ),
        (
            report["stage4_rare_comparison"],
            report["stage4_rare_comparison_sha256"],
        ),
    )
    for relative, expected_hash in hashed_outputs:
        path = ROOT / relative
        require(path)
        if sha256_file(path) != expected_hash:
            fail(f"creature artifact hash mismatch: {relative}")

    assets = report.get("assets", [])
    if (
        tuple(asset.get("id") for asset in assets) != contract.creature_ids
        or report.get("palette_ids") != list(contract.palette_ids)
    ):
        fail("creature report species count or palette ordinal contract changed")
    for asset in assets:
        source = ROOT / asset["source"]
        require(source)
        if sha256_file(source) != asset["source_sha256"]:
            fail(f"creature source hash mismatch: {asset['id']}")
        authored = asset.get("authored_animation")
        if authored:
            for path_key, hash_key in (
                ("manifest", "manifest_sha256"),
                ("report", "report_sha256"),
                ("reviewed_spritesheet", "reviewed_spritesheet_sha256"),
            ):
                path = ROOT / authored[path_key]
                require(path)
                if sha256_file(path) != authored[hash_key]:
                    fail(
                        "creature authored animation hash mismatch: "
                        f"{asset['id']} {path_key}"
                    )
        if any(asset["probe_changed_protected_pixels"]):
            fail(f"creature probe changed protected anatomy: {asset['id']}")
        if any(
            any(values)
            for values in asset["stage3_changed_protected_pixels"].values()
        ):
            fail(f"creature pattern changed protected anatomy: {asset['id']}")
        if any(asset["stage4_changed_outside_rare_safe_pixels"]):
            fail(
                "creature rare treatment escaped its authored region: "
                f"{asset['id']}"
            )
        frame_checks = asset.get("frame_checks", [])
        if len(frame_checks) != contract.frame_count or not all(
            all(check.values()) for check in frame_checks
        ):
            fail(f"creature frame gate failed: {asset['id']}")


def verify_letter_card_asset() -> None:
    report_path = ROOT / "art/letter_cards/generated/stone_card_report.json"
    require(report_path)
    report = json.loads(report_path.read_text())
    if (report.get("status") != "passed" or
            report.get("selected_direction") != "2A v6 tone-on-tone stonewash with Atkinson" or
            report.get("production_asset") is not True or
            report.get("openai_image_generation_used") is not False or
            report.get("new_generation_calls") != 0):
        fail("selected letter-card production report is invalid")
    if report.get("source_sha256") != EXPECTED_STONE_SOURCE_SHA256:
        fail("selected letter-card source identity changed")
    if report.get("review_contact_sheet_sha256") != EXPECTED_STONE_REVIEW_SHA256:
        fail("selected letter-card visual review identity changed")

    for path_key, hash_key in (
        ("builder", "builder_sha256"),
        ("source", "source_sha256"),
        ("review_contact_sheet", "review_contact_sheet_sha256"),
        ("header", "header_sha256"),
    ):
        path = ROOT / report[path_key]
        require(path)
        if sha256_file(path) != report[hash_key]:
            fail(f"letter-card {path_key} differs from its audited report")

    review_manifest_path = (
        ROOT / "art/generated/one_off/letter_card_surfaces_2026-08-25/"
        "alphabet_extrapolation_stone_wide_palette/render_manifest.json"
    )
    require(review_manifest_path)
    if sha256_file(review_manifest_path) != report.get("review_manifest_sha256"):
        fail("letter-card review manifest differs from its audited report")
    review_manifest = json.loads(review_manifest_path.read_text())
    if (review_manifest.get("output", {}).get("sha256") !=
            EXPECTED_STONE_REVIEW_SHA256):
        fail("letter-card review manifest points to a different sheet")
    if (review_manifest.get("selected_font") !=
            "Atkinson Hyperlegible Next ExtraBold 800" or
            review_manifest.get("selected_font_source_sha256") !=
            EXPECTED_ATKINSON_SOURCE_SHA256):
        fail("letter-card review does not use the selected Atkinson face")
    if review_manifest.get("role_color_policy") != (
            "all eight visible RD semantic regions are narrow lightness steps "
            "derived from each letter base; no fixed cyan or navy texture colors"):
        fail("letter-card review does not use the tone-on-tone role policy")
    if report.get("review_role_color_policy") != review_manifest.get(
            "role_color_policy"):
        fail("letter-card report does not pin the tone-on-tone role policy")
    for path_key, hash_key in (
        ("selected_font_header", "selected_font_header_sha256"),
        ("card_renderer", "card_renderer_sha256"),
    ):
        path = ROOT / review_manifest[path_key]
        require(path)
        if sha256_file(path) != review_manifest[hash_key]:
            fail(f"letter-card review {path_key} changed after rendering")

    expected_counts = {
        "transparent": 68,
        "main_body": 7066,
        "body_shadow": 853,
        "deep_crevice": 647,
        "pale_mineral": 517,
        "deep_slate": 501,
        "mid_mineral": 237,
        "white_chip": 28,
        "cyan_glint": 27,
    }
    if (report.get("semantic_dimensions") != [88, 113] or
            report.get("semantic_role_counts") != expected_counts or
            report.get("packed_bytes") != 4972 or
            sum(expected_counts.values()) != 88 * 113):
        fail("letter-card semantic packing contract changed")
    palette = report.get("palette", [])
    if len(palette) != 26 or len(set(palette)) != 26:
        fail("letter-card palette must contain 26 unique fixed colors")


def verify_selected_letter_font() -> None:
    report_path = ROOT / "art/fonts/generated/atkinson_hyperlegible_next_report.json"
    require(report_path)
    report = json.loads(report_path.read_text())
    if (report.get("status") != "passed" or
            report.get("selected_font") != "Atkinson Hyperlegible Next" or
            report.get("selected_weight") != "ExtraBold 800" or
            report.get("nominal_pixel_size") != 112 or
            report.get("glyph_range") != "a-z" or
            report.get("source_sha256") != EXPECTED_ATKINSON_SOURCE_SHA256 or
            report.get("selection_contact_sheet_sha256") !=
            EXPECTED_ATKINSON_CONTACT_SHA256 or
            report.get("card_size") != [138, 158] or
            report.get("halo_radius") != 2 or
            report.get("all_glyphs_fit") is not True):
        fail("selected Atkinson letter-font report is invalid")
    for path_key, hash_key in (
        ("builder", "builder_sha256"),
        ("selection_contact_sheet", "selection_contact_sheet_sha256"),
        ("header", "header_sha256"),
    ):
        path = ROOT / report[path_key]
        require(path)
        if sha256_file(path) != report[hash_key]:
            fail(f"selected letter font {path_key} differs from its report")
    glyphs = report.get("glyphs", [])
    if (len(glyphs) != 26 or
            "".join(item.get("letter", "") for item in glyphs) !=
            "abcdefghijklmnopqrstuvwxyz" or
            not all(item.get("halo_fit") is True for item in glyphs)):
        fail("selected Atkinson glyph roster or card fit is invalid")


def verify_replay_button_asset() -> None:
    report_path = ROOT / "art/replay_button/generated/deep_loop_report.json"
    require(report_path)
    report = json.loads(report_path.read_text())
    if (report.get("status") != "passed" or
            report.get("selected_direction") != "3 - Deep loop" or
            report.get("production_asset") is not True or
            report.get("vendor") != "retrodiffusion" or
            report.get("provider_model") != "rd_pro" or
            report.get("prompt_style") != "rd_pro__simple" or
            report.get("seed") != 82563 or
            report.get("openai_image_generation_used") is not False or
            report.get("new_generation_calls") != 0):
        fail("selected Deep loop replay-button report is invalid")
    if (report.get("source_sha256") != EXPECTED_REPLAY_SOURCE_SHA256 or
            report.get("source_metadata_sha256") !=
            EXPECTED_REPLAY_METADATA_SHA256 or
            report.get("header_sha256") != EXPECTED_REPLAY_HEADER_SHA256):
        fail("selected Deep loop replay-button identity changed")
    for path_key, hash_key in (
        ("builder", "builder_sha256"),
        ("source", "source_sha256"),
        ("source_metadata", "source_metadata_sha256"),
        ("header", "header_sha256"),
    ):
        path = ROOT / report[path_key]
        require(path)
        if sha256_file(path) != report[hash_key]:
            fail(f"replay-button {path_key} differs from its audited report")
    if (report.get("source_size") != [64, 64] or
            report.get("alpha_bbox") != [1, 1, 63, 63] or
            report.get("opaque_pixels") != 3024 or
            report.get("transparent_pixels") != 1072 or
            report.get("connected_opaque_components") != 1 or
            report.get("connected_play_glyph_components") != 1 or
            report.get("play_glyph_bbox") != [24, 19, 46, 45] or
            report.get("packed_bytes") != 2048 or
            report.get("packed_sha256") != EXPECTED_REPLAY_PACKED_SHA256 or
            report.get("palette_rgb565") != [
                "0x0000", "0x00A4", "0x0947", "0x124C", "0x332F",
                "0x5C74", "0x95B7", "0xDF7E", "0xF7FF",
            ] or
            report.get("role_pixel_counts") !=
            [1072, 539, 2, 922, 590, 4, 1, 637, 329]):
        fail("selected Deep loop replay-button packing contract changed")


def verify_break_timer_asset() -> None:
    report_path = ROOT / "art/break_timer/generated/tideglass_report.json"
    require(report_path)
    report = json.loads(report_path.read_text())
    if (report.get("status") != "passed" or
            report.get("selected_direction") != "2 - Shell-inlay glass" or
            report.get("production_asset") is not True or
            report.get("vendor") != "retrodiffusion" or
            report.get("provider_model") != "rd_pro" or
            report.get("prompt_style") != "rd_pro__simple" or
            report.get("seed") != 82802 or
            report.get("task_id") !=
            "58783246-31be-4cac-bafc-9226bd75ee44" or
            report.get("openai_image_generation_used") is not False or
            report.get("provider_reported_balance_cost") != 0.18 or
            report.get("candidate_generation_calls") != 3 or
            report.get("candidate_generation_balance_cost_total") != 0.54):
        fail("selected break-timer report is invalid")
    if (report.get("source_sha256") != EXPECTED_BREAK_TIMER_SOURCE_SHA256 or
            report.get("source_metadata_sha256") !=
            EXPECTED_BREAK_TIMER_METADATA_SHA256 or
            report.get("header_sha256") != EXPECTED_BREAK_TIMER_HEADER_SHA256):
        fail("selected break-timer identity changed")
    for path_key, hash_key in (
        ("builder", "builder_sha256"),
        ("source", "source_sha256"),
        ("source_metadata", "source_metadata_sha256"),
        ("header", "header_sha256"),
        ("preview_renderer", "preview_renderer_sha256"),
    ):
        path = ROOT / report[path_key]
        require(path)
        if sha256_file(path) != report[hash_key]:
            fail(f"break-timer {path_key} differs from its audited report")
    evidence = report.get("selection_evidence", [])
    if (len(evidence) != 10 or
            len({item.get("path") for item in evidence}) != 10):
        fail("break-timer selection evidence roster is invalid")
    for item in evidence:
        path = ROOT / item["path"]
        require(path)
        if sha256_file(path) != item.get("sha256"):
            fail(f"break-timer selection evidence changed: {item['path']}")
    if (report.get("source_size") != [128, 128] or
            report.get("alpha_bbox") != [23, 1, 105, 128] or
            report.get("opaque_pixels") != 8078 or
            report.get("transparent_pixels") != 8306 or
            report.get("connected_opaque_components") != 1 or
            report.get("packed_bytes") != 8192 or
            report.get("packed_sha256") != EXPECTED_BREAK_TIMER_PACKED_SHA256 or
            report.get("palette_rgb565") != [
                "0x0000", "0x00A4", "0x0947", "0x124C", "0x332F",
                "0x5C74", "0x95B7", "0xDF7E", "0xF5AD", "0xF713",
            ] or
            report.get("role_pixel_counts") !=
            [8306, 1885, 283, 1338, 2280, 506, 152, 316, 1313, 5]):
        fail("selected break-timer packing contract changed")


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
    application = (build_dir / "PhonicsGame.ino.bin").read_bytes()
    if application[0xB0:0xD0] != b"\0" * 32:
        fail("application contains non-canonical host-derived ELF metadata")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path)
    args = parser.parse_args()
    for relative in (
        "firmware/PhonicsGame/PhonicsGame.ino",
        "firmware/PhonicsGame/CardStoneRendering.h",
        "firmware/PhonicsGame/ReplayButtonAsset.h",
        "firmware/PhonicsGame/BreakTimerAsset.h",
        "scripts/preview_break_timer.py",
        "firmware/PhonicsGame/fonts/AtkinsonHyperlegibleNextExtraBold112.h",
        "firmware/PhonicsGame/fonts/NunitoBold28.h",
        "config/toolchain.env",
        "firmware/BUILD_MANIFEST.json",
        "scripts/canonicalize_firmware.py",
        "PRODUCT_SPEC.md",
    ):
        require(ROOT / relative)
    verify_vendor()
    verify_build_contract()
    verify_audio()
    verify_creature_assets()
    verify_letter_card_asset()
    verify_selected_letter_font()
    verify_replay_button_asset()
    verify_break_timer_asset()
    if args.build_dir:
        verify_build(args.build_dir.resolve())
    print("Repository payload verified")


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
