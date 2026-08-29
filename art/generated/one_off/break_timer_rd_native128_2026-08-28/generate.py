#!/usr/bin/env python3
"""Generate untouched native 128x128 Retro Diffusion break-timer icons."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
RD_OUT = OUT / "retrodiffusion"
TASKS_PATH = OUT / "tasks.json"
API_ROOT = "https://api.retrodiffusion.ai/v1"
STYLE = "rd_pro__simple"
SOURCE_SIZE = (128, 128)

# Match the accepted Deep loop and water-creature family while reserving the
# two warm colors for sand. Purple and pink are intentionally absent from this
# calm, non-reward screen.
PALETTE = [
    "#071522", "#0B2A3C", "#124A60", "#35677A", "#5F8FA0",
    "#91B7BE", "#D8EEF0", "#F7FFFF", "#27D3D0", "#2588D8",
    "#F3B56B", "#F4E39B",
]

SHARED = (
    "A single complete 128 by 128 low-resolution pixel-art ocean tideglass icon for the rest screen of a toddler "
    "phonics toy. One large unmistakable hourglass centered on a genuinely transparent canvas, filling most of the "
    "canvas while keeping every outline pixel visible. Flat front view, child-readable silhouette, broad clean pixel "
    "clusters, dark navy contour, deep teal glass, moon-pale highlights, and restrained warm sand. Original game UI "
    "design matching a calm deep-sea stone-and-current visual family. Strictly one connected object. No text, letters, "
    "numbers, colon, clock face, animal, face, scenery, seabed, plants, loose bubbles, cast shadow, detached pixels, "
    "checkerboard, colored square, glow, multiple objects, crop, clipping, antialiasing, or one-pixel noise. "
)

CANDIDATES = [
    {
        "id": "tideglass_stone",
        "label": "1 - Tide-stone glass",
        "seed": 82801,
        "prompt": (
            "A chunky carved tide-stone top and base joined by two gently curved side pillars. A broad transparent "
            "teal glass chamber holds one clear mound of pale golden sand below and a smaller amount above. Quiet "
            "asymmetrical chips echo the accepted stone letter cards without making the silhouette busy."
        ),
    },
    {
        "id": "tideglass_shell",
        "label": "2 - Shell-inlay glass",
        "seed": 82802,
        "prompt": (
            "A rounded dark-slate hourglass frame with two subtle shell-ridge inlays contained inside its broad top "
            "and base. Deep teal glass, one narrow sand stream, and a large warm sand mound. Soft, sturdy proportions "
            "with no ornate curls, pearls, or decorative objects."
        ),
    },
    {
        "id": "tideglass_current",
        "label": "3 - Deep-current glass",
        "seed": 82803,
        "prompt": (
            "A deep navy and teal hourglass whose two thick side supports curve like one calm tidal loop while still "
            "reading immediately as an hourglass. Moon-pale glass edges, a bold golden sand stream, and a broad sand "
            "mound. Minimal interior detail and no separate wave or ring."
        ),
    },
]


def encode_png(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def palette_b64(colors: list[str]) -> str:
    palette = Image.new("RGB", (len(colors), 1))
    for index, color in enumerate(colors):
        palette.putpixel((index, 0), ImageColor.getrgb(color))
    return encode_png(palette)


def request_json(url: str, key: str, payload: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "X-RD-Token": key},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"Retro Diffusion HTTP {exc.code}: {body[:1000]}") from exc


def load_tasks() -> dict:
    if TASKS_PATH.exists():
        return json.loads(TASKS_PATH.read_text())
    return {"schema_version": 1, "tasks": {}}


def save_tasks(tasks: dict) -> None:
    TASKS_PATH.write_text(json.dumps(tasks, indent=2) + "\n")


def submit(candidate: dict, key: str) -> str:
    result = request_json(
        f"{API_ROOT}/inferences",
        key,
        {
            "prompt": SHARED + candidate["prompt"],
            "prompt_style": STYLE,
            "width": SOURCE_SIZE[0],
            "height": SOURCE_SIZE[1],
            "num_images": 1,
            "seed": candidate["seed"],
            "remove_bg": True,
            "input_palette": palette_b64(PALETTE),
            "bypass_prompt_expansion": True,
            "async_process": True,
        },
    )
    if not result.get("task_id"):
        raise RuntimeError(f"Retro Diffusion did not return a task id: {result}")
    return result["task_id"]


def poll(task_id: str, key: str) -> dict:
    while True:
        state = request_json(f"{API_ROOT}/inferences/tasks/{task_id}", key)
        status = state.get("status")
        if status in {"pending", "running", "accepted"}:
            time.sleep(2)
            continue
        if status == "succeeded":
            return state["result"]
        raise RuntimeError(
            f"Retro Diffusion task {task_id} ended with {status}: {state.get('error')}"
        )


def save(candidate: dict, task_id: str, result: dict) -> dict:
    RD_OUT.mkdir(parents=True, exist_ok=True)
    path = RD_OUT / f"{candidate['id']}__{candidate['seed']}.png"
    path.write_bytes(base64.b64decode(result["base64_images"][0]))
    with Image.open(path) as image:
        image.load()
        if image.size != SOURCE_SIZE or image.mode != "RGBA":
            raise RuntimeError(
                f"{path} is {image.size} {image.mode}, expected {SOURCE_SIZE} RGBA"
            )
        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        corners_clear = all(
            image.getpixel(point)[3] == 0
            for point in ((0, 0), (127, 0), (0, 127), (127, 127))
        )
        alpha_values = sorted(set(alpha.getdata()))
    metadata = {
        "schema_version": 1,
        "vendor": "retrodiffusion",
        "asset_id": candidate["id"],
        "label": candidate["label"],
        "seed": candidate["seed"],
        "task_id": task_id,
        "prompt": SHARED + candidate["prompt"],
        "prompt_style": STYLE,
        "response": {
            "balance_cost": result.get("balance_cost"),
            "model": result.get("model"),
        },
        "source_size": list(SOURCE_SIZE),
        "source_mode": "RGBA",
        "alpha_bbox": list(bbox) if bbox else None,
        "alpha_values": alpha_values,
        "corner_transparency_gate_passed": corners_clear,
        "postprocess": "none; PNG bytes are the untouched Retro Diffusion task result",
        "png_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "png": str(path.relative_to(ROOT)),
    }
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def load_saved(candidate: dict, task_id: str) -> dict | None:
    path = RD_OUT / f"{candidate['id']}__{candidate['seed']}.png"
    metadata_path = path.with_suffix(".json")
    if not path.exists() and not metadata_path.exists():
        return None
    if not path.is_file() or not metadata_path.is_file():
        raise RuntimeError(f"partial saved Retro Diffusion result for {candidate['id']}")
    metadata = json.loads(metadata_path.read_text())
    expected = {
        "vendor": "retrodiffusion",
        "asset_id": candidate["id"],
        "seed": candidate["seed"],
        "task_id": task_id,
        "prompt_style": STYLE,
        "png_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise RuntimeError(f"saved {candidate['id']} has invalid {key}")
    return metadata


GLYPHS = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ":": ("0", "0", "1", "0", "1", "0", "0"),
}


def draw_countdown(draw: ImageDraw.ImageDraw, text: str, y: int) -> None:
    scale = 7
    gap = 7
    widths = [len(GLYPHS[character][0]) * scale for character in text]
    total = sum(widths) + gap * (len(text) - 1)
    x = (368 - total) // 2
    for character, width in zip(text, widths):
        for row, pattern in enumerate(GLYPHS[character]):
            for column, value in enumerate(pattern):
                if value == "1":
                    draw.rectangle(
                        (
                            x + column * scale,
                            y + row * scale,
                            x + (column + 1) * scale - 1,
                            y + (row + 1) * scale - 1,
                        ),
                        fill="#D8EEF0",
                    )
        x += width + gap


def device_mock(sample: dict) -> Image.Image:
    screen = Image.new("RGB", (368, 448), "#000000")
    icon = Image.open(ROOT / sample["png"]).convert("RGBA")
    screen.paste(icon, (120, 54), icon)
    draw = ImageDraw.Draw(screen)
    draw_countdown(draw, "30:00", 238)
    draw.rounded_rectangle((64, 334, 303, 341), radius=4, fill="#0B2A3C")
    draw.ellipse((61, 332, 70, 343), fill="#F4E39B")
    font = ImageFont.load_default(size=20)
    label_box = draw.textbbox((0, 0), "rest", font=font)
    label_width = label_box[2] - label_box[0]
    draw.text(((368 - label_width) // 2, 375), "rest", fill="#5F8FA0", font=font)
    return screen


def contact_sheet(samples: list[dict]) -> Path:
    title = ImageFont.load_default(size=24)
    label = ImageFont.load_default(size=18)
    note = ImageFont.load_default(size=14)
    sheet = Image.new("RGB", (1206, 940), "#071522")
    draw = ImageDraw.Draw(sheet)
    draw.text((22, 16), "Native 128x128 Retro Diffusion tideglass candidates", fill="#F7FFFF", font=title)
    for column, sample in enumerate(samples):
        x0 = column * 402
        color = "#F4E39B" if sample["corner_transparency_gate_passed"] else "#E06C8C"
        draw.text((x0 + 18, 58), sample["label"], fill=color, font=label)
        checker = Image.new("RGBA", (256, 256), "#0B2A3C")
        checker_draw = ImageDraw.Draw(checker)
        for yy in range(0, 256, 16):
            for xx in range(0, 256, 16):
                if (xx // 16 + yy // 16) % 2:
                    checker_draw.rectangle((xx, yy, xx + 15, yy + 15), fill="#124A60")
        candidate = Image.open(ROOT / sample["png"]).convert("RGBA")
        checker.alpha_composite(candidate.resize((256, 256), Image.Resampling.NEAREST))
        sheet.paste(checker.convert("RGB"), (x0 + 73, 92))
        sheet.paste(device_mock(sample), (x0 + 17, 380))
        gate = "PASS" if sample["corner_transparency_gate_passed"] else "FAIL"
        draw.text(
            (x0 + 18, 850),
            f"native 128px, untouched PNG | corners {gate}",
            fill="#91B7BE",
            font=note,
        )
        draw.text(
            (x0 + 18, 878),
            f"seed {sample['seed']} | alpha {sample['alpha_bbox']}",
            fill="#91B7BE",
            font=note,
        )
    path = OUT / "contact_sheet.png"
    sheet.save(path, optimize=True)
    return path


def main() -> int:
    key = (
        os.environ.get("RETRODIFFUSION_API_KEY", "")
        or os.environ.get("retrodiffusion_api_key", "")
    )
    if not key:
        raise SystemExit("Missing RETRODIFFUSION_API_KEY")
    tasks = load_tasks()
    for candidate in CANDIDATES:
        if candidate["id"] not in tasks["tasks"]:
            print(f"submit {candidate['id']} seed={candidate['seed']}", flush=True)
            tasks["tasks"][candidate["id"]] = {"task_id": submit(candidate, key)}
            save_tasks(tasks)
    samples = []
    for candidate in CANDIDATES:
        task_id = tasks["tasks"][candidate["id"]]["task_id"]
        saved = load_saved(candidate, task_id)
        if saved is not None:
            print(f"reuse  {candidate['id']} task={task_id}", flush=True)
            samples.append(saved)
            continue
        print(f"poll   {candidate['id']} task={task_id}", flush=True)
        samples.append(save(candidate, task_id, poll(task_id, key)))
    sheet = contact_sheet(samples)
    summary = {
        "schema_version": 1,
        "purpose": "Three untouched native 128x128 RD break-timer icon candidates.",
        "vendor": "retrodiffusion",
        "prompt_style": STYLE,
        "generation_call_count": len(samples),
        "passing_candidate_count": sum(
            1 for sample in samples if sample["corner_transparency_gate_passed"]
        ),
        "retrodiffusion_reported_balance_cost_total": round(
            sum(float(sample["response"].get("balance_cost") or 0) for sample in samples),
            4,
        ),
        "postprocess": (
            "none on candidate PNGs; contact sheet enlarges raw pixels and composites "
            "native 128px outputs without cropping"
        ),
        "contact_sheet": str(sheet.relative_to(ROOT)),
        "samples": samples,
    }
    (OUT / "generation_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
