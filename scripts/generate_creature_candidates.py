#!/usr/bin/env python3
"""Generate review candidates with the sprite-specific services used by Dream Duel.

This is an authoring command. The checked-in production pack remains sufficient
for normal firmware builds; API keys are never needed at build or runtime.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
CREATURE_ROOT = ROOT / "creatures"
MANIFEST_PATH = CREATURE_ROOT / "creature_manifest.json"
OUTPUT_ROOT = CREATURE_ROOT / "generated" / "candidates"

THEME = (
    "Production-ready low-resolution pixel-art water-creature sprite for a tiny portrait AMOLED. "
    "Original design with a strong readable silhouette, restrained interior detail, crisp opaque pixel edges, "
    "one dark outline, medium shading, and luminous ocean accents. Strictly one subject on a genuinely transparent "
    "background. Inspired only by the general readability and underwater adventure mood of polished side-view diving "
    "games; do not reproduce any existing game's creature design, sprite, composition, or exact palette."
)


def load_env(path: Path | None) -> None:
    if not path or not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 180) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:1000]}") from exc


def decode_image(value: str) -> bytes:
    if value.startswith("data:"):
        value = value.split(",", 1)[1]
    return base64.b64decode(value)


def palette_base64(palette: list[str]) -> str:
    colors = [value for value in palette if len(value) == 7]
    image = Image.new("RGB", (len(colors), 1))
    for index, color in enumerate(colors):
        image.putpixel((index, 0), ImageColor.getrgb(color))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def complete_prompt(asset: dict) -> str:
    return f"{THEME} {asset['prompt']}"


def generate_pixellab(asset: dict, seed: int, palette: list[str], api_key: str) -> tuple[bytes, dict]:
    payload = {
        "description": complete_prompt(asset),
        "image_size": {"width": 128, "height": 128},
        "text_guidance_scale": 9,
        "outline": "single color black outline",
        "shading": "medium shading",
        "detail": "medium detail",
        "view": "side",
        "no_background": True,
        "background_removal_task": "remove_simple_background",
        "color_image": {"type": "base64", "base64": palette_base64(palette), "format": "png"},
        "seed": seed,
    }
    if asset["facing"] in {"east", "west"}:
        payload["direction"] = asset["facing"]
    result = post_json(
        "https://api.pixellab.ai/v2/create-image-pixflux",
        payload,
        {"Authorization": f"Bearer {api_key}"},
    )
    return decode_image(result["image"]["base64"]), {
        "usage": result.get("usage"),
        "model": result.get("model", "pixflux"),
    }


def generate_retrodiffusion(asset: dict, seed: int, palette: list[str], api_key: str) -> tuple[bytes, dict]:
    payload = {
        "prompt": complete_prompt(asset),
        "prompt_style": "rd_pro__simple",
        "width": 128,
        "height": 128,
        "num_images": 1,
        "seed": seed,
        "remove_bg": True,
        "input_palette": palette_base64(palette),
    }
    result = post_json(
        "https://api.retrodiffusion.ai/v1/inferences",
        payload,
        {"X-RD-Token": api_key},
    )
    return decode_image(result["base64_images"][0]), {
        "balance_cost": result.get("balance_cost"),
        "model": result.get("model"),
    }


def save_candidate(vendor: str, asset: dict, seed: int, image_bytes: bytes, response: dict) -> None:
    vendor_dir = OUTPUT_ROOT / vendor
    vendor_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{asset['id']}__{seed}"
    image_path = vendor_dir / f"{stem}.png"
    image_path.write_bytes(image_bytes)
    with Image.open(image_path) as generated:
        generated.load()
        if generated.size != (128, 128):
            raise RuntimeError(f"{image_path} is {generated.size}, expected 128x128")
        alpha_bbox = generated.convert("RGBA").getchannel("A").getbbox()
    metadata = {
        "schema_version": 1,
        "vendor": vendor,
        "asset_id": asset["id"],
        "seed": seed,
        "prompt": complete_prompt(asset),
        "response": response,
        "source_size": [128, 128],
        "alpha_bbox": list(alpha_bbox) if alpha_bbox else None,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    image_path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def make_contact_sheet(manifest: dict) -> Path:
    seeds = manifest["generation"]["seeds"]
    samples = [(vendor, seed) for vendor in manifest["generation"]["vendors"] for seed in seeds]
    tile_size = 256
    label_height = 42
    header_height = 54
    margin = 18
    width = margin * 2 + len(samples) * tile_size
    height = header_height + len(manifest["assets"]) * (tile_size + label_height) + margin
    sheet = Image.new("RGB", (width, height), "#071522")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    small = ImageFont.load_default(size=13)
    for column, (vendor, seed) in enumerate(samples):
        draw.text((margin + column * tile_size + 8, 18), f"{vendor} · {seed}", fill="#D8EEF0", font=font)
    for row, asset in enumerate(manifest["assets"]):
        y = header_height + row * (tile_size + label_height)
        for column, (vendor, seed) in enumerate(samples):
            x = margin + column * tile_size
            checker = Image.new("RGBA", (tile_size, tile_size), "#0B2A3C")
            checker_draw = ImageDraw.Draw(checker)
            for yy in range(0, tile_size, 16):
                for xx in range(0, tile_size, 16):
                    if (xx // 16 + yy // 16) % 2:
                        checker_draw.rectangle((xx, yy, xx + 15, yy + 15), fill="#124A60")
            path = OUTPUT_ROOT / vendor / f"{asset['id']}__{seed}.png"
            if path.exists():
                candidate = Image.open(path).convert("RGBA").resize((tile_size, tile_size), Image.Resampling.NEAREST)
                checker.alpha_composite(candidate)
            else:
                checker_draw.text((18, 112), "missing", fill="#E06C8C", font=font)
            sheet.paste(checker.convert("RGB"), (x, y))
        draw.text((margin + 8, y + tile_size + 10), asset["label"], fill="#F4E39B", font=small)
    destination = OUTPUT_ROOT / "contact_sheet.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, optimize=True)
    return destination


def write_summary(manifest: dict) -> None:
    samples: list[dict] = []
    retro_cost = 0.0
    for metadata_path in sorted(OUTPUT_ROOT.glob("*/*.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        response = metadata.get("response", {})
        cost = float(response.get("balance_cost") or 0.0)
        retro_cost += cost
        samples.append({
            "vendor": metadata["vendor"],
            "asset_id": metadata["asset_id"],
            "seed": metadata["seed"],
            "alpha_bbox": metadata["alpha_bbox"],
            "reported_balance_cost": cost or None,
            "usage": response.get("usage"),
        })
    summary = {
        "schema_version": 1,
        "sample_count": len(samples),
        "expected_sample_count": len(manifest["assets"]) * len(manifest["generation"]["seeds"]) * len(manifest["generation"]["vendors"]),
        "retrodiffusion_reported_balance_cost_total": round(retro_cost, 4),
        "note": "PixelLab usage is retained verbatim when supplied; the service response may not expose a USD amount.",
        "samples": samples,
    }
    (OUTPUT_ROOT / "generation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", choices=["pixellab", "retrodiffusion", "both"], default="both")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sheet-only", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    load_env(args.env_file)
    if args.sheet_only:
        print(make_contact_sheet(manifest))
        write_summary(manifest)
        return 0

    pixellab_key = os.environ.get("PIXELLAB_API_KEY", "")
    retro_key = os.environ.get("retrodiffusion_api_key", "") or os.environ.get("RETRODIFFUSION_API_KEY", "")
    vendors = manifest["generation"]["vendors"] if args.vendor == "both" else [args.vendor]
    if "pixellab" in vendors and not pixellab_key:
        raise SystemExit("Missing PIXELLAB_API_KEY (use --env-file or the environment)")
    if "retrodiffusion" in vendors and not retro_key:
        raise SystemExit("Missing retrodiffusion_api_key (use --env-file or the environment)")

    jobs = []
    for asset in manifest["assets"]:
        for seed in manifest["generation"]["seeds"]:
            for vendor in vendors:
                destination = OUTPUT_ROOT / vendor / f"{asset['id']}__{seed}.png"
                if destination.exists() and not args.force:
                    print(f"skip {vendor:15} {asset['id']} seed={seed}")
                    continue
                jobs.append((vendor, asset, seed))

    def run_job(job: tuple[str, dict, int]) -> str:
        vendor, asset, seed = job
        print(f"run  {vendor:15} {asset['id']} seed={seed}", flush=True)
        if vendor == "pixellab":
            image_bytes, response = generate_pixellab(asset, seed, manifest["palette"], pixellab_key)
        else:
            image_bytes, response = generate_retrodiffusion(asset, seed, manifest["palette"], retro_key)
        save_candidate(vendor, asset, seed, image_bytes, response)
        return f"done {vendor:15} {asset['id']} seed={seed}"

    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        future_to_job = {executor.submit(run_job, job): job for job in jobs}
        for future in concurrent.futures.as_completed(future_to_job):
            vendor, asset, seed = future_to_job[future]
            try:
                print(future.result(), flush=True)
            except Exception as exc:
                failure = f"{vendor}/{asset['id']}/{seed}: {exc}"
                failures.append(failure)
                print(f"FAIL {failure}", file=sys.stderr, flush=True)

    make_contact_sheet(manifest)
    write_summary(manifest)
    if failures:
        (OUTPUT_ROOT / "failures.txt").write_text("\n".join(failures) + "\n", encoding="utf-8")
        return 1
    (OUTPUT_ROOT / "failures.txt").unlink(missing_ok=True)
    print(OUTPUT_ROOT / "contact_sheet.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
