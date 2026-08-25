#!/usr/bin/env python3
"""Generate one preview-only Retro Diffusion pass for rare creature concepts."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import generate_creature_style_bakeoff as bakeoff


ROOT = Path(__file__).resolve().parents[1]
CONCEPT_ROOT = ROOT / "creatures" / "rare_concepts"
MANIFEST_PATH = CONCEPT_ROOT / "concept_manifest.json"
OUTPUT_ROOT = CONCEPT_ROOT / "generated"


def raw_path(animal: dict) -> Path:
    return OUTPUT_ROOT / "raw" / f"{animal['id']}__{animal['seed']}.png"


def save_candidate(manifest: dict, animal: dict, data: bytes, response: dict) -> None:
    destination = raw_path(animal)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    with Image.open(destination) as image:
        image.load()
        if image.size != (128, 128):
            raise RuntimeError(f"{destination} is {image.size}, expected 128x128")
        bbox = image.convert("RGBA").getchannel("A").getbbox()
    metadata = {
        "schema_version": 1,
        "status": "preview_only_not_runtime",
        "style_id": manifest["style"]["id"],
        "vendor": "retrodiffusion",
        "animal_id": animal["id"],
        "seed": animal["seed"],
        "prompt": bakeoff.prompt_for(manifest, manifest["style"], animal),
        "response": response,
        "alpha_bbox": list(bbox) if bbox else None,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    destination.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def make_contact_sheet(manifest: dict) -> Path:
    columns = 5
    panel_width, panel_height = 368, 448
    label_height = 42
    gap = 10
    header_height = 60
    rows = (len(manifest["animals"]) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (gap + columns * (panel_width + gap), header_height + gap + rows * (panel_height + label_height + gap)),
        "#07131C",
    )
    draw = ImageDraw.Draw(sheet)
    title_font = ImageFont.load_default(size=18)
    label_font = ImageFont.load_default(size=15)
    draw.text((18, 18), "RARE CREATURES · ONE-OFF RETRO DIFFUSION PASS", fill="#E8F4F2", font=title_font)

    for index, animal in enumerate(manifest["animals"]):
        row, column = divmod(index, columns)
        x = gap + column * (panel_width + gap)
        y = header_height + gap + row * (panel_height + label_height + gap)
        with Image.open(raw_path(animal)) as source:
            sprite = bakeoff.normalize_for_display(source, animal["logical_size"], manifest["style"])
        panel = bakeoff.render_device_cell(sprite, manifest["render_scale"])
        sheet.paste(panel, (x, y))
        draw.text((x + 8, y + panel_height + 11), animal["label"], fill="#F0D996", font=label_font)

    destination = OUTPUT_ROOT / "rare_creature_contact_sheet.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, optimize=True)
    return destination


def write_summary(manifest: dict) -> Path:
    samples = []
    total_cost = 0.0
    for animal in manifest["animals"]:
        metadata = json.loads(raw_path(animal).with_suffix(".json").read_text(encoding="utf-8"))
        cost = float(metadata.get("response", {}).get("balance_cost") or 0.0)
        total_cost += cost
        samples.append({
            "animal_id": animal["id"],
            "seed": animal["seed"],
            "reported_balance_cost": cost or None,
            "alpha_bbox": metadata.get("alpha_bbox"),
        })
    summary = {
        "schema_version": 1,
        "status": "preview_only_not_runtime",
        "sample_count": len(samples),
        "retrodiffusion_reported_balance_cost_total": round(total_cost, 4),
        "note": "Retro Diffusion reports balance-cost units, not a USD value.",
        "samples": samples,
    }
    destination = OUTPUT_ROOT / "generation_summary.json"
    destination.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sheet-only", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if args.sheet_only:
        print(make_contact_sheet(manifest))
        print(write_summary(manifest))
        return 0

    bakeoff.load_env(args.env_file)
    api_key = os.environ.get("retrodiffusion_api_key", "") or os.environ.get("RETRODIFFUSION_API_KEY", "")
    if not api_key:
        raise SystemExit("Missing RETRODIFFUSION_API_KEY")

    jobs = [animal for animal in manifest["animals"] if args.force or not raw_path(animal).exists()]

    def generate(animal: dict) -> str:
        print(f"run  retrodiffusion {animal['id']} seed={animal['seed']}", flush=True)
        data, response = bakeoff.generate_retro(manifest, manifest["style"], animal, api_key)
        save_candidate(manifest, animal, data, response)
        return f"done retrodiffusion {animal['id']} seed={animal['seed']}"

    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(generate, animal): animal for animal in jobs}
        for future in concurrent.futures.as_completed(futures):
            animal = futures[future]
            try:
                print(future.result(), flush=True)
            except Exception as exc:
                failures.append(f"{animal['id']}: {exc}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1

    print(make_contact_sheet(manifest))
    print(write_summary(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
