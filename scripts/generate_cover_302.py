#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate platform covers with the locked whiteboard thumbnail style via 302ai."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gpt-image-2-t2i"

PLATFORM_PRESETS: dict[str, tuple[int, int, str]] = {
    "youtube": (1280, 720, "horizontal 16:9 video thumbnail"),
    "bilibili": (1280, 720, "horizontal 16:9 video thumbnail"),
    "wechat": (1280, 720, "horizontal 16:9 video thumbnail"),
    "xiaohongshu": (1440, 1920, "vertical 3:4 social cover"),
    "douyin": (1080, 1920, "vertical 9:16 short-video cover"),
    "kuaishou": (1080, 1920, "vertical 9:16 short-video cover"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a 302.ai cover image using the locked editorial whiteboard style.",
    )
    parser.add_argument("--title", required=True, help="Main Chinese title to render on the cover.")
    parser.add_argument("--subtitle", default="", help="Short highlight badge text.")
    parser.add_argument("--topic", default="", help="Content/topic context for the illustration.")
    parser.add_argument("--subject", default="", help="Central visual subject, e.g. beer glass, rocket, coffee cup.")
    parser.add_argument("--left-context", default="", help="Left/top context scene for the composition.")
    parser.add_argument("--right-context", default="", help="Right/bottom context scene for the composition.")
    parser.add_argument(
        "--timeline",
        default="",
        help="Optional timeline labels separated by |, e.g. 1万年前|苏美尔|中世纪|工业革命|今天.",
    )
    parser.add_argument("--platform", default="youtube", help=f"Preset platform: {', '.join(PLATFORM_PRESETS)}")
    parser.add_argument("--width", type=int, help="Override output width.")
    parser.add_argument("--height", type=int, help="Override output height.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="302.ai text-to-image model.")
    parser.add_argument("--output", type=Path, help="Output image path.")
    parser.add_argument("--prompt-out", type=Path, help="Prompt text output path.")
    parser.add_argument("--output-format", default="png", choices=["png", "jpg", "jpeg", "webp"])
    parser.add_argument("--quality", default="high", choices=["auto", "low", "medium", "high"])
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--sync", action="store_true", help="Use blocking image generate instead of async create/fetch.")
    parser.add_argument("--dry-run", action="store_true", help="Write/print prompt only; do not call 302ai.")
    parser.add_argument("--print-prompt", action="store_true", help="Print the generated prompt.")
    return parser.parse_args()


def slugify(value: str, fallback: str = "cover") -> str:
    ascii_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()
    return ascii_slug or fallback


def platform_dimensions(platform: str, width: int | None, height: int | None) -> tuple[int, int, str]:
    key = platform.lower().strip()
    if key not in PLATFORM_PRESETS and (not width or not height):
        supported = ", ".join(sorted(PLATFORM_PRESETS))
        raise SystemExit(f"Unknown platform '{platform}'. Use --width and --height, or choose: {supported}")
    preset_width, preset_height, description = PLATFORM_PRESETS.get(key, (width or 1280, height or 720, "custom cover"))
    return width or preset_width, height or preset_height, description


def default_output_path(platform: str, title: str, output_format: str) -> Path:
    suffix = "jpg" if output_format == "jpeg" else output_format
    slug = slugify(title, f"cover-{platform}")
    return REPO_ROOT / "output" / "covers" / f"{slug}_{platform}.{suffix}"


def compact(value: str) -> str:
    return " ".join(value.split()).strip()


def build_prompt(args: argparse.Namespace, width: int, height: int, platform_description: str) -> str:
    orientation = "horizontal" if width >= height else "vertical"
    title = compact(args.title)
    subtitle = compact(args.subtitle)
    topic = compact(args.topic)
    subject = compact(args.subject) or "the most important object from the title and topic"
    left_context = compact(args.left_context) or "historical origin or root-cause scene from the topic"
    right_context = compact(args.right_context) or "modern consequence or present-day scene from the topic"
    timeline = [compact(item) for item in args.timeline.split("|") if compact(item)]
    timeline_text = " | ".join(timeline[:6]) if timeline else "infer 4 to 6 short milestone labels from the topic"
    subtitle_line = f'Exact small amber badge text: "{subtitle}".' if subtitle else "Add one short amber badge with the core number or hook."

    layout = (
        "For horizontal covers: large title at the top, central large subject icon, "
        "left historical scene, right modern scene, and a bottom timeline arrow."
        if orientation == "horizontal"
        else "For vertical covers: large title at the top, amber badge below it, central large subject icon, "
        "stacked historical and modern mini-scenes, and a compact bottom timeline."
    )

    return f"""
Create a premium editorial whiteboard thumbnail cover for a Chinese explainer video.
Canvas: {width}x{height}, {platform_description}, {orientation} composition.

LOCKED STYLE:
- Clean whiteboard marker infographic illustration.
- One mathematically flat warm off-white background #F6F1E3.
- Dark charcoal black marker linework, restrained amber accent only.
- Abstract faceless round-headed people only: no facial features, no hair, no realistic portraits.
- Hand-drawn black marker typography with readable Chinese text.
- Image-first design; text supports the image.

CONTENT:
- Exact large Chinese title: "{title}".
- {subtitle_line}
- Topic context: {topic or title}.
- Central main subject: {subject}.
- Left / early context: {left_context}.
- Right / modern context: {right_context}.
- Timeline micro-labels: {timeline_text}.

COMPOSITION:
- {layout}
- Keep the image structured, premium, calm, and easy to understand at thumbnail size.
- Use at most: one title, one highlight badge, and 4 to 6 tiny timeline labels.
- Tiny labels must be short, readable, and secondary to the drawing.

AVOID:
- Do not fill the image with paragraphs, lists, dense Chinese text, captions, or poster clutter.
- No photorealism, no 3D rendering, no gradients, no textured paper, no smiley faces.
- No local white patches, no beige-white halos around drawings, no cutout boxes.
- No extra fonts added in post-production; all text must be naturally drawn in the image.
""".strip()


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise ValueError("302ai returned empty stdout")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)
    if candidates:
        return candidates[-1]
    raise ValueError(f"Could not parse 302ai JSON output: {text[:500]}")


def run_302ai(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"302ai command failed ({result.returncode}): {message[:1200]}")
    return parse_json_stdout(result.stdout)


def result_url(data: dict[str, Any]) -> str:
    for key in ("result_url", "image_url", "url"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    image_urls = data.get("image_urls")
    if isinstance(image_urls, list) and image_urls and isinstance(image_urls[0], str):
        return image_urls[0]
    raise RuntimeError(f"302ai response did not contain an image URL: {json.dumps(data, ensure_ascii=False)[:1000]}")


def output_format_args(args: argparse.Namespace) -> list[str]:
    # The current 302.AI gpt-image-2 endpoint rejects output_format even
    # though the CLI exposes it as a common image option.
    if args.model == "gpt-image-2-t2i":
        return []
    return ["--output_format", args.output_format]


def create_image_async(args: argparse.Namespace, prompt: str, width: int, height: int) -> str:
    extra = json.dumps({"quality": args.quality, "n": 1}, ensure_ascii=False)
    create_data = run_302ai(
        [
            "302ai",
            "image",
            "create",
            "--prompt",
            prompt,
            "--model",
            args.model,
            "--width",
            str(width),
            "--height",
            str(height),
            *output_format_args(args),
            "--extra",
            extra,
        ]
    )
    if create_data.get("status") == "completed":
        return result_url(create_data)
    if create_data.get("status") == "failed":
        raise RuntimeError(json.dumps(create_data, ensure_ascii=False))

    taskid = create_data.get("taskid")
    if not isinstance(taskid, str) or not taskid:
        raise RuntimeError(f"302ai did not return a taskid: {json.dumps(create_data, ensure_ascii=False)[:1000]}")

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        time.sleep(args.poll_interval)
        fetch_data = run_302ai(["302ai", "image", "fetch", taskid, "--short"])
        status = fetch_data.get("status")
        if status == "completed":
            return result_url(fetch_data)
        if status == "failed":
            raise RuntimeError(json.dumps(fetch_data, ensure_ascii=False))
    raise TimeoutError(f"Timed out waiting for 302ai image task {taskid}")


def create_image_sync(args: argparse.Namespace, prompt: str, width: int, height: int) -> str:
    extra = json.dumps({"quality": args.quality, "n": 1}, ensure_ascii=False)
    data = run_302ai(
        [
            "302ai",
            "image",
            "generate",
            "--prompt",
            prompt,
            "--model",
            args.model,
            "--width",
            str(width),
            "--height",
            str(height),
            *output_format_args(args),
            "--extra",
            extra,
        ]
    )
    if data.get("status") == "failed":
        raise RuntimeError(json.dumps(data, ensure_ascii=False))
    return result_url(data)


def download(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "whiteboard-cover-generator/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        output_path.write_bytes(response.read())


def main() -> int:
    args = parse_args()
    width, height, platform_description = platform_dimensions(args.platform, args.width, args.height)
    output_path = args.output or default_output_path(args.platform, args.title, args.output_format)
    prompt_path = args.prompt_out or output_path.with_suffix(output_path.suffix + ".prompt.txt")
    prompt = build_prompt(args, width, height, platform_description)

    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt + "\n", encoding="utf-8")

    if args.print_prompt or args.dry_run:
        print(prompt)
    if args.dry_run:
        print(f"[DRY RUN] Prompt written to: {prompt_path}")
        print(f"[DRY RUN] Output would be: {output_path}")
        return 0

    if not os.environ.get("AI302_KEY"):
        print("[WARN] AI302_KEY is not set in the current environment. 302ai may still work if configured globally.", file=sys.stderr)

    image_url = create_image_sync(args, prompt, width, height) if args.sync else create_image_async(args, prompt, width, height)
    download(image_url, output_path)

    print("[OK] Cover generated")
    print(f"  image:  {output_path}")
    print(f"  prompt: {prompt_path}")
    print(f"  size:   {width}x{height}")
    print(f"  model:  {args.model}")
    print(f"  quality:{args.quality}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
