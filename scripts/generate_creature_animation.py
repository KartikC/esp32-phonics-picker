#!/usr/bin/env python3
"""Author a review-only Retro Diffusion creature animation sprite sheet.

This command is deliberately outside the normal build. It preserves the raw
provider result and never promotes generated frames into firmware. A separate
review step must register, bound, palette-map, and approve every frame first.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "creatures" / "animation" / "shark_chomp_manifest.json"
API_BASE = "https://api.retrodiffusion.ai/v1"
POLL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 15 * 60


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_env(path: Path | None) -> None:
    if not path or not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api_key() -> str:
    key = (
        os.environ.get("RETRODIFFUSION_API_KEY", "")
        or os.environ.get("retrodiffusion_api_key", "")
        or os.environ.get("RD_API_KEY", "")
    )
    if not key:
        raise SystemExit(
            "Missing RETRODIFFUSION_API_KEY, retrodiffusion_api_key, or RD_API_KEY"
        )
    return key


def request_json(
    method: str,
    url: str,
    key: str,
    payload: dict | None = None,
    timeout: int = 180,
) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-RD-Token": key,
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"Retro Diffusion HTTP {exc.code}: {detail}") from exc


def service_status() -> dict:
    request = urllib.request.Request(f"{API_BASE}/status", method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def subject_image(manifest: dict, source_path: Path) -> Image.Image:
    with Image.open(source_path) as source:
        source.load()
        rgba = source.convert("RGBA")
    if list(rgba.size) != manifest["source_canvas"]:
        raise RuntimeError(
            f"source size {rgba.size} does not match {manifest['source_canvas']}"
        )
    canvas = Image.new("RGBA", tuple(manifest["conditioning_canvas"]), (0, 0, 0, 0))
    canvas.alpha_composite(rgba, tuple(manifest["source_offset"]))
    return canvas


def conditioning_image(subject: Image.Image, manifest: dict) -> Image.Image:
    background = ImageColor.getrgb(manifest["conditioning_background"])
    canvas = Image.new("RGB", subject.size, background)
    canvas.paste(subject.convert("RGB"), (0, 0), subject.getchannel("A"))
    return canvas


def palette_base64(colors: list[str]) -> str:
    palette = Image.new("RGB", (len(colors), 1))
    for index, color in enumerate(colors):
        palette.putpixel((index, 0), ImageColor.getrgb(color))
    return base64.b64encode(png_bytes(palette)).decode("ascii")


def png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def provider_payload(manifest: dict, input_png: bytes) -> dict:
    provider = manifest["provider"]
    width, height = manifest["conditioning_canvas"]
    return {
        "prompt": manifest["prompt"],
        "prompt_style": provider["prompt_style"],
        "width": width,
        "height": height,
        "num_images": 1,
        "frames_duration": provider["frames_duration"],
        "return_spritesheet": True,
        "seed": provider["generation_seed"],
        "input_image": base64.b64encode(input_png).decode("ascii"),
        "input_palette": palette_base64(manifest["palette"]),
        "remove_bg": True,
        "upload_outputs": True,
    }


def public_payload(payload: dict, input_sha256: str) -> dict:
    result = dict(payload)
    result["input_image"] = f"sha256:{input_sha256}"
    return result


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def poll_task(task_id: str, key: str) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_status = None
    while time.monotonic() < deadline:
        task = request_json(
            "GET", f"{API_BASE}/inferences/tasks/{urllib.parse.quote(task_id)}", key,
            timeout=60,
        )
        status = task.get("status")
        if status != last_status:
            print(f"task {task_id}: {status}", flush=True)
            last_status = status
        if status == "succeeded":
            result = task.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("succeeded task has no result object")
            return result
        if status == "failed":
            raise RuntimeError(f"Retro Diffusion task failed: {task.get('error')}")
        time.sleep(POLL_SECONDS)
    raise TimeoutError(
        f"task {task_id} is still incomplete after {POLL_TIMEOUT_SECONDS} seconds; "
        "resume with --resume " + task_id
    )


def fetch_provider_bytes(result: dict) -> tuple[bytes, str | None]:
    encoded = result.get("base64_images") or []
    if encoded:
        value = encoded[0]
        if value.startswith("data:"):
            value = value.split(",", 1)[1]
        return base64.b64decode(value), None
    urls = result.get("output_urls") or []
    if not urls:
        raise RuntimeError("provider result contains neither base64_images nor output_urls")
    url = urls[0]
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError(f"refusing non-HTTPS provider output URL: {url}")
    with urllib.request.urlopen(url, timeout=180) as response:
        return response.read(), url


def extract_frames(data: bytes, frame_size: tuple[int, int], count: int) -> tuple[list[Image.Image], str]:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        image_format = (image.format or "").upper()
        if getattr(image, "n_frames", 1) == count:
            frames = []
            for index in range(count):
                image.seek(index)
                frames.append(image.convert("RGBA"))
            return frames, image_format or "GIF"

        width, height = image.size
        frame_width, frame_height = frame_size
        if width % frame_width or height % frame_height:
            raise RuntimeError(
                f"provider sheet {image.size} is not divisible by frame size {frame_size}"
            )
        columns = width // frame_width
        rows = height // frame_height
        if columns * rows != count:
            raise RuntimeError(
                f"provider sheet {image.size} contains {columns * rows} cells, expected {count}"
            )
        rgba = image.convert("RGBA")
        frames = [
            rgba.crop((
                column * frame_width,
                row * frame_height,
                (column + 1) * frame_width,
                (row + 1) * frame_height,
            ))
            for row in range(rows)
            for column in range(columns)
        ]
        return frames, image_format or "PNG"


def alpha_iou(left: Image.Image, right: Image.Image) -> float:
    left_alpha = [
        value >= 128 for value in left.getchannel("A").get_flattened_data()
    ]
    right_alpha = [
        value >= 128 for value in right.getchannel("A").get_flattened_data()
    ]
    intersection = sum(a and b for a, b in zip(left_alpha, right_alpha))
    union = sum(a or b for a, b in zip(left_alpha, right_alpha))
    return intersection / union if union else 1.0


def save_review_artifacts(
    output_dir: Path,
    raw_data: bytes,
    frames: list[Image.Image],
    conditioning: Image.Image,
    subject: Image.Image,
    result: dict,
    output_url: str | None,
    manifest: dict,
    input_sha256: str,
    detected_format: str,
    manifest_path: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_name = "provider_spritesheet.png" if detected_format == "PNG" else "provider_animation.gif"
    raw_path = output_dir / raw_name
    raw_path.write_bytes(raw_data)
    conditioning_path = output_dir / "conditioning_frame_rgb.png"
    conditioning.save(conditioning_path, optimize=True)
    subject_path = output_dir / "conditioning_subject_rgba.png"
    subject.save(subject_path, optimize=True)

    frame_records = []
    for index, frame in enumerate(frames):
        frame_path = output_dir / f"provider_frame_{index}.png"
        frame.save(frame_path, optimize=True)
        alpha = frame.getchannel("A")
        frame_records.append({
            "index": index,
            "path": str(frame_path.relative_to(ROOT)),
            "sha256": sha256_file(frame_path),
            "alpha_bounds": list(alpha.getbbox()) if alpha.getbbox() else None,
            "opaque_pixels": sum(
                value >= 128 for value in alpha.get_flattened_data()
            ),
            "conditioning_alpha_iou": round(alpha_iou(frame, subject), 6),
        })

    cell_width, cell_height = conditioning.size
    contact = Image.new("RGBA", (cell_width * len(frames), cell_height), "#071522")
    for index, frame in enumerate(frames):
        tile = Image.new("RGBA", frame.size, "#071522")
        draw = ImageDraw.Draw(tile)
        for y in range(0, tile.height, 8):
            for x in range(0, tile.width, 8):
                if (x // 8 + y // 8) % 2:
                    draw.rectangle((x, y, x + 7, y + 7), fill="#0B2A3C")
        tile.alpha_composite(frame)
        contact.alpha_composite(tile, (index * cell_width, 0))
    contact_path = output_dir / "provider_contact_sheet.png"
    contact.convert("RGB").save(contact_path, optimize=True)
    animation_path = output_dir / "provider_preview.gif"
    frames[0].save(
        animation_path,
        save_all=True,
        append_images=frames[1:],
        duration=180,
        loop=0,
        disposal=2,
        transparency=0,
    )

    report = {
        "schema_version": 1,
        "status": "provider_output_requires_manual_review",
        "manifest": str(manifest_path.relative_to(ROOT)),
        "manifest_sha256": sha256_file(manifest_path),
        "input_sha256": input_sha256,
        "raw_output": str(raw_path.relative_to(ROOT)),
        "raw_output_sha256": sha256_file(raw_path),
        "provider_format": detected_format,
        "provider_delivery": "output_url" if output_url else "base64",
        "balance_cost": result.get("balance_cost"),
        "remaining_balance": result.get("remaining_balance"),
        "model": result.get("model"),
        "frames": frame_records,
        "contact_sheet": str(contact_path.relative_to(ROOT)),
        "contact_sheet_sha256": sha256_file(contact_path),
        "preview_animation": str(animation_path.relative_to(ROOT)),
        "preview_animation_sha256": sha256_file(animation_path),
        "review_contract": manifest["review_contract"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(output_dir / "provider_report.json", report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-cost", action="store_true")
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--resume", metavar="TASK_ID")
    parser.add_argument(
        "--yes", action="store_true",
        help="confirm the paid provider call when used with --generate",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_path = ROOT / manifest["source"]
    if sha256_file(source_path) != manifest["source_sha256"]:
        raise SystemExit("selected source SHA-256 does not match animation manifest")
    load_env(args.env_file)
    key = api_key()
    subject = subject_image(manifest, source_path)
    conditioning = conditioning_image(subject, manifest)
    input_data = png_bytes(conditioning)
    input_sha256 = sha256_bytes(input_data)
    payload = provider_payload(manifest, input_data)
    output_dir = ROOT / manifest["output_dir"]

    if not args.resume:
        cost_result = request_json(
            "POST", manifest["provider"]["endpoint"], key,
            {**payload, "check_cost": True},
        )
        cost = float(cost_result.get("balance_cost") or 0.0)
        maximum = float(manifest["provider"]["maximum_cost_usd"])
        print(
            f"Retro Diffusion preflight: ${cost:.3f}; "
            f"remaining balance ${float(cost_result.get('remaining_balance') or 0.0):.3f}"
        )
        if cost > maximum:
            raise SystemExit(f"cost ${cost:.3f} exceeds manifest ceiling ${maximum:.3f}")
        if args.check_cost or not args.generate:
            return 0

        if not args.yes:
            raise SystemExit("--generate requires --yes after the free cost preflight")

    if not args.resume and (output_dir / "provider_report.json").exists() and not args.force:
        raise SystemExit(f"review output already exists at {output_dir}; pass --force explicitly")

    status = service_status()
    animation_status = status.get("status", {}).get("animations")
    if animation_status in {"down", "error", "unavailable"}:
        raise SystemExit(f"Retro Diffusion animation service is not ready: {animation_status!r}")
    if animation_status != "ok":
        print(
            f"warning: animation service health is {animation_status!r}; "
            "the exact request still passed provider cost validation",
            flush=True,
        )

    if args.resume:
        task_id = args.resume
    else:
        accepted = request_json(
            "POST", manifest["provider"]["endpoint"], key,
            {**payload, "async": True},
        )
        task_id = accepted.get("task_id")
        if not task_id:
            raise RuntimeError(f"async submission returned no task_id: {accepted}")
        write_json(output_dir / "job.json", {
            "schema_version": 1,
            "status": accepted.get("status"),
            "task_id": task_id,
            "request": public_payload(payload, input_sha256),
            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        print(f"submitted Retro Diffusion task {task_id}", flush=True)

    result = poll_task(task_id, key)
    raw_data, output_url = fetch_provider_bytes(result)
    frame_size = tuple(manifest["conditioning_canvas"])
    frames, detected_format = extract_frames(
        raw_data, frame_size, manifest["provider"]["frames_duration"]
    )
    if any(frame.size != frame_size for frame in frames):
        raise RuntimeError("provider returned an unexpected animation frame size")
    save_review_artifacts(
        output_dir, raw_data, frames, conditioning, subject, result, output_url,
        manifest, input_sha256, detected_format, manifest_path,
    )
    print(output_dir / "provider_contact_sheet.png")
    print(output_dir / "provider_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
