#!/usr/bin/env python3
"""Generate a four-style, four-animal external-model comparison sheet."""

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
BAKEOFF_ROOT = ROOT / "creatures" / "style_bakeoff"
MANIFEST_PATH = BAKEOFF_ROOT / "style_manifest.json"
OUTPUT_ROOT = BAKEOFF_ROOT / "generated"


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


def palette_base64(colors: list[str]) -> str:
    opaque = [value for value in colors if len(value) == 7]
    image = Image.new("RGB", (len(opaque), 1))
    for index, color in enumerate(opaque):
        image.putpixel((index, 0), ImageColor.getrgb(color))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def decode_image(value: str) -> bytes:
    if value.startswith("data:"):
        value = value.split(",", 1)[1]
    return base64.b64decode(value)


def prompt_for(manifest: dict, style: dict, animal: dict) -> str:
    return (
        "Production-ready original low-resolution pixel-art sea-animal game sprite. "
        f"Subject: {animal['prompt']}. "
        f"Visual direction: {style['brief']}. "
        "It will be normalized to a coarse logical grid and enlarged exactly 3x on a 368 by 448 portrait AMOLED, "
        "so prioritize large coherent pixel clusters and instant silhouette recognition at arm's length. "
        f"Constraints: {manifest['shared_constraints']}. "
        "Use broad aesthetic principles only; do not reproduce any existing commercial game's sprite, character, composition, or exact palette."
    )


def generate_pixellab(manifest: dict, style: dict, animal: dict, key: str) -> tuple[bytes, dict]:
    prompt = prompt_for(manifest, style, animal)
    payload = {
        "description": prompt,
        "image_size": {"width": 128, "height": 128},
        "text_guidance_scale": 9,
        "outline": "single color black outline",
        "shading": "medium shading",
        "detail": "low detail",
        "view": "side",
        "no_background": True,
        "background_removal_task": "remove_simple_background",
        "color_image": {"type": "base64", "base64": palette_base64(style["palette"]), "format": "png"},
        "seed": animal["seed"],
    }
    if animal["id"] != "moon_jelly":
        payload["direction"] = "east"
    result = post_json(
        "https://api.pixellab.ai/v2/create-image-pixflux",
        payload,
        {"Authorization": f"Bearer {key}"},
    )
    return decode_image(result["image"]["base64"]), {
        "model": result.get("model", "pixflux"),
        "usage": result.get("usage"),
    }


def generate_retro(manifest: dict, style: dict, animal: dict, key: str) -> tuple[bytes, dict]:
    prompt = prompt_for(manifest, style, animal)
    payload = {
        "prompt": prompt,
        "prompt_style": "rd_pro__simple",
        "width": 128,
        "height": 128,
        "num_images": 1,
        "seed": animal["seed"],
        "remove_bg": True,
        "input_palette": palette_base64(style["palette"]),
    }
    result = post_json(
        "https://api.retrodiffusion.ai/v1/inferences",
        payload,
        {"X-RD-Token": key},
    )
    return decode_image(result["base64_images"][0]), {
        "model": result.get("model"),
        "balance_cost": result.get("balance_cost"),
    }


def exact_palette(style: dict) -> list[tuple[int, int, int, int]]:
    result = []
    for value in style["palette"]:
        if len(value) == 9:
            result.append(ImageColor.getcolor(value, "RGBA"))
        else:
            result.append((*ImageColor.getrgb(value), 255))
    return result


def normalize_for_display(source: Image.Image, logical_size: list[int], style: dict) -> Image.Image:
    rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
    rgba.putalpha(alpha)
    bbox = alpha.getbbox()
    if not bbox:
        raise ValueError("candidate is blank")
    cropped = rgba.crop(bbox)
    width, height = logical_size
    content_width, content_height = width - 8, height - 8
    scale = min(content_width / cropped.width, content_height / cropped.height)
    resized = cropped.resize((max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))), Image.Resampling.NEAREST)
    placed = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    placed.alpha_composite(resized, ((width - resized.width) // 2, (height - resized.height) // 2))

    palette = exact_palette(style)
    opaque = palette[1:]
    output = Image.new("RGBA", placed.size, (0, 0, 0, 0))
    pixels = []
    for red, green, blue, alpha_value in placed.get_flattened_data():
        if alpha_value < 128:
            pixels.append((0, 0, 0, 0))
            continue
        index = min(
            range(len(opaque)),
            key=lambda candidate: (
                (red - opaque[candidate][0]) ** 2
                + (green - opaque[candidate][1]) ** 2
                + (blue - opaque[candidate][2]) ** 2
            ),
        )
        pixels.append(opaque[index])
    output.putdata(pixels)
    return output


def candidate_path(style: dict, animal: dict) -> Path:
    return OUTPUT_ROOT / "raw" / style["id"] / f"{animal['id']}__{animal['seed']}.png"


def save_candidate(manifest: dict, style: dict, animal: dict, data: bytes, response: dict) -> None:
    path = candidate_path(style, animal)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    with Image.open(path) as image:
        image.load()
        if image.size != (128, 128):
            raise RuntimeError(f"{path} is {image.size}, expected 128x128")
        bbox = image.convert("RGBA").getchannel("A").getbbox()
    metadata = {
        "schema_version": 1,
        "style_id": style["id"],
        "style_label": style["label"],
        "vendor": style["vendor"],
        "animal_id": animal["id"],
        "seed": animal["seed"],
        "prompt": prompt_for(manifest, style, animal),
        "response": response,
        "alpha_bbox": list(bbox) if bbox else None,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def render_device_cell(sprite: Image.Image, scale: int) -> Image.Image:
    panel = Image.new("RGB", (368, 448), "#02070C")
    enlarged = sprite.resize((sprite.width * scale, sprite.height * scale), Image.Resampling.NEAREST)
    x = (panel.width - enlarged.width) // 2
    y = (panel.height - enlarged.height) // 2
    panel.paste(enlarged, (x, y), enlarged)
    return panel


def make_comparison(manifest: dict) -> Path:
    styles = manifest["styles"]
    animals = manifest["animals"]
    cell_width, cell_height = 368, 448
    left_label = 150
    header = 60
    gap = 10
    sheet = Image.new(
        "RGB",
        (left_label + len(styles) * (cell_width + gap) + gap, header + len(animals) * (cell_height + gap) + gap),
        "#07131C",
    )
    draw = ImageDraw.Draw(sheet)
    title_font = ImageFont.load_default(size=17)
    label_font = ImageFont.load_default(size=15)
    for column, style in enumerate(styles):
        x = left_label + column * (cell_width + gap)
        draw.text((x + 8, 20), style["label"], fill="#E8F4F2", font=title_font)
    for row, animal in enumerate(animals):
        y = header + row * (cell_height + gap)
        draw.text((12, y + 20), animal["label"], fill="#F0D996", font=label_font)
        draw.text((12, y + 44), f"{animal['logical_size'][0]}x{animal['logical_size'][1]} @3x", fill="#88AEB5", font=label_font)
        for column, style in enumerate(styles):
            path = candidate_path(style, animal)
            with Image.open(path) as source:
                sprite = normalize_for_display(source, animal["logical_size"], style)
            panel = render_device_cell(sprite, manifest["render_scale"])
            x = left_label + column * (cell_width + gap)
            sheet.paste(panel, (x, y))
    destination = OUTPUT_ROOT / "style_comparison.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, optimize=True)

    for style in styles:
        option = Image.new("RGB", (cell_width * 2 + gap, cell_height * 2 + gap + 44), "#07131C")
        option_draw = ImageDraw.Draw(option)
        option_draw.text((12, 14), style["label"], fill="#E8F4F2", font=title_font)
        for index, animal in enumerate(animals):
            with Image.open(candidate_path(style, animal)) as source:
                sprite = normalize_for_display(source, animal["logical_size"], style)
            panel = render_device_cell(sprite, manifest["render_scale"])
            x = (index % 2) * (cell_width + gap)
            y = 44 + (index // 2) * (cell_height + gap)
            option.paste(panel, (x, y))
        option.save(OUTPUT_ROOT / f"{style['id']}.png", optimize=True)
    return destination


def write_summary(manifest: dict) -> None:
    samples = []
    retro_cost = 0.0
    for metadata_path in sorted((OUTPUT_ROOT / "raw").glob("*/*.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        cost = float(metadata.get("response", {}).get("balance_cost") or 0.0)
        retro_cost += cost
        samples.append({
            "style_id": metadata["style_id"],
            "vendor": metadata["vendor"],
            "animal_id": metadata["animal_id"],
            "seed": metadata["seed"],
            "reported_balance_cost": cost or None,
            "usage": metadata.get("response", {}).get("usage"),
        })
    summary = {
        "schema_version": 1,
        "sample_count": len(samples),
        "expected_sample_count": len(manifest["styles"]) * len(manifest["animals"]),
        "retrodiffusion_reported_balance_cost_total": round(retro_cost, 4),
        "note": "Retro Diffusion reports balance-cost units, not a USD value. PixelLab reports generation count when available.",
        "samples": samples,
    }
    (OUTPUT_ROOT / "generation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sheet-only", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    load_env(args.env_file)
    if args.sheet_only:
        print(make_comparison(manifest))
        write_summary(manifest)
        return 0

    pixellab_key = os.environ.get("PIXELLAB_API_KEY", "")
    retro_key = os.environ.get("retrodiffusion_api_key", "") or os.environ.get("RETRODIFFUSION_API_KEY", "")
    if any(style["vendor"] == "pixellab" for style in manifest["styles"]) and not pixellab_key:
        raise SystemExit("Missing PIXELLAB_API_KEY")
    if any(style["vendor"] == "retrodiffusion" for style in manifest["styles"]) and not retro_key:
        raise SystemExit("Missing RETRODIFFUSION_API_KEY")

    jobs = []
    for style in manifest["styles"]:
        for animal in manifest["animals"]:
            path = candidate_path(style, animal)
            if path.exists() and not args.force:
                print(f"skip {style['id']:24} {animal['id']}")
                continue
            jobs.append((style, animal))

    def run(job: tuple[dict, dict]) -> str:
        style, animal = job
        print(f"run  {style['id']:24} {animal['id']}", flush=True)
        if style["vendor"] == "pixellab":
            data, response = generate_pixellab(manifest, style, animal, pixellab_key)
        else:
            data, response = generate_retro(manifest, style, animal, retro_key)
        save_candidate(manifest, style, animal, data, response)
        return f"done {style['id']:24} {animal['id']}"

    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(run, job): job for job in jobs}
        for future in concurrent.futures.as_completed(futures):
            style, animal = futures[future]
            try:
                print(future.result(), flush=True)
            except Exception as exc:
                failure = f"{style['id']}/{animal['id']}: {exc}"
                failures.append(failure)
                print(f"FAIL {failure}", file=sys.stderr, flush=True)

    if failures:
        (OUTPUT_ROOT / "failures.txt").write_text("\n".join(failures) + "\n", encoding="utf-8")
        return 1
    (OUTPUT_ROOT / "failures.txt").unlink(missing_ok=True)
    destination = make_comparison(manifest)
    write_summary(manifest)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
