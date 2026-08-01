#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create local config files and write user-provided API keys.

This script intentionally writes only ignored local files:
- auto-whiteboard/config/config.ini
- skills/whiteboard-video-workflow/.env
"""

from __future__ import annotations

import argparse
import configparser
import getpass
import os
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_EXAMPLE = REPO_ROOT / "auto-whiteboard" / "config" / "config.example.ini"
CONFIG_PATH = REPO_ROOT / "auto-whiteboard" / "config" / "config.ini"
ENV_EXAMPLE = REPO_ROOT / "skills" / "whiteboard-video-workflow" / ".env.example"
ENV_PATH = REPO_ROOT / "skills" / "whiteboard-video-workflow" / ".env"

PROVIDERS = {
    "apimart": "apimart_image2",
    "apimart_image2": "apimart_image2",
    "kie": "kie_image2",
    "kie_image2": "kie_image2",
    "t8": "t8_image2",
    "t8_image2": "t8_image2",
    "macode": "macode_image2",
    "macode_image2": "macode_image2",
}


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "<set>"
    return f"{value[:4]}...{value[-4:]}"


def prompt_secret(label: str, current: str = "") -> str:
    suffix = f" [{mask(current)}]" if current else ""
    value = getpass.getpass(f"{label}{suffix}: ").strip()
    return value or current


def copy_if_missing(src: Path, dst: Path) -> None:
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def ensure_config() -> configparser.ConfigParser:
    copy_if_missing(CONFIG_EXAMPLE, CONFIG_PATH)
    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_PATH, encoding="utf-8-sig")
    return config


def set_option(config: configparser.ConfigParser, section: str, option: str, value: str) -> None:
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, option, str(value))


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env(values: dict[str, str]) -> None:
    ordered_keys = [
        "AI302_KEY",
        "IMAGE_PROVIDER",
        "APIMART_BASE_URL",
        "APIMART_API_KEY",
        "APIMART_IMAGE_MODEL",
        "APIMART_IMAGE_SIZE",
        "APIMART_IMAGE_RESOLUTION",
        "APIMART_IMAGE_CONCURRENCY",
        "APIMART_IMAGE_TIMEOUT",
        "APIMART_IMAGE_POLL_INTERVAL",
        "KIE_BASE_URL",
        "KIE_API_KEY",
        "KIE_IMAGE_MODEL",
        "KIE_IMAGE_RESOLUTION",
        "KIE_IMAGE_CONCURRENCY",
        "KIE_IMAGE_TIMEOUT",
        "KIE_IMAGE_POLL_INTERVAL",
        "T8_BASE_URL",
        "T8_API_KEY",
        "T8_IMAGE_MODEL",
        "T8_IMAGE_SIZE",
        "T8_IMAGE_QUALITY",
        "T8_IMAGE_CONCURRENCY",
        "T8_IMAGE_ASYNC",
        "MACODE_BASE_URL",
        "MACODE_API_KEY",
        "MACODE_IMAGE_MODEL",
        "MACODE_IMAGE_SIZE",
        "MACODE_IMAGE_QUALITY",
        "MACODE_IMAGE_CONCURRENCY",
        "RUNNINGHUB_API_KEY",
    ]
    lines = ["# Local image provider settings. Do not commit this file."]
    for key in ordered_keys:
        if key in values:
            lines.append(f"{key}={values[key]}")
    for key in sorted(set(values) - set(ordered_keys)):
        lines.append(f"{key}={values[key]}")
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def default_env_values() -> dict[str, str]:
    copy_if_missing(ENV_EXAMPLE, ENV_PATH)
    values = read_env(ENV_PATH)
    values.setdefault("AI302_KEY", "")
    values.setdefault("IMAGE_PROVIDER", "apimart_image2")
    values.setdefault("APIMART_BASE_URL", "https://api.apimart.ai/v1")
    values.setdefault("APIMART_IMAGE_MODEL", "gpt-image-2")
    values.setdefault("APIMART_IMAGE_SIZE", "1792x1008")
    values.setdefault("APIMART_IMAGE_RESOLUTION", "1k")
    values.setdefault("APIMART_IMAGE_CONCURRENCY", "16")
    values.setdefault("APIMART_IMAGE_TIMEOUT", "600")
    values.setdefault("APIMART_IMAGE_POLL_INTERVAL", "5")
    values.setdefault("KIE_BASE_URL", "https://api.kie.ai")
    values.setdefault("KIE_IMAGE_MODEL", "gpt-image-2-text-to-image")
    values.setdefault("KIE_IMAGE_RESOLUTION", "1k")
    values.setdefault("KIE_IMAGE_CONCURRENCY", "16")
    values.setdefault("KIE_IMAGE_TIMEOUT", "600")
    values.setdefault("KIE_IMAGE_POLL_INTERVAL", "5")
    values.setdefault("T8_BASE_URL", "https://ai.t8star.cn/v1")
    values.setdefault("T8_IMAGE_MODEL", "gpt-image-2")
    values.setdefault("T8_IMAGE_SIZE", "1792x1008")
    values.setdefault("T8_IMAGE_QUALITY", "high")
    values.setdefault("T8_IMAGE_CONCURRENCY", "16")
    values.setdefault("T8_IMAGE_ASYNC", "true")
    values.setdefault("MACODE_IMAGE_MODEL", "gpt-image-2")
    values.setdefault("MACODE_IMAGE_SIZE", "1792x1008")
    values.setdefault("MACODE_IMAGE_QUALITY", "high")
    values.setdefault("MACODE_IMAGE_CONCURRENCY", "8")
    return values


def provider_key_name(provider: str) -> str:
    return {
        "apimart_image2": "APIMART_API_KEY",
        "kie_image2": "KIE_API_KEY",
        "t8_image2": "T8_API_KEY",
        "macode_image2": "MACODE_API_KEY",
    }[provider]


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure local API keys for the whiteboard video workflow")
    parser.add_argument("--tts-key", help="MiniMax/302 API key")
    parser.add_argument("--tts-api-url", default="https://api.302.ai/minimaxi/v1/t2a_v2")
    parser.add_argument("--tts-voice-id", default="Chinese (Mandarin)_Warm_Bestie")
    parser.add_argument("--image-provider", default="apimart_image2")
    parser.add_argument("--image-key", help="Image provider API key")
    parser.add_argument("--cover-key", help="Optional 302.AI key used for cover generation")
    parser.add_argument("--image-base-url", help="Override image provider base URL")
    parser.add_argument("--image-concurrency", type=int, default=16)
    parser.add_argument("--whiteboard-jobs", type=int, default=max(1, min(4, (os.cpu_count() or 4) // 2)))
    parser.add_argument("--non-interactive", action="store_true", help="Fail instead of prompting for missing keys")
    args = parser.parse_args()

    provider = PROVIDERS.get(args.image_provider, args.image_provider)
    if provider not in set(PROVIDERS.values()):
        supported = ", ".join(sorted(PROVIDERS))
        raise SystemExit(f"Unsupported image provider: {args.image_provider}. Supported: {supported}")
    config = ensure_config()
    env_values = default_env_values()

    tts_key = args.tts_key or config.get("MiniMax", "api_key", fallback="")
    image_key_name = provider_key_name(provider)
    image_key = args.image_key or env_values.get(image_key_name, "")
    cover_key = args.cover_key or env_values.get("AI302_KEY", "") or os.environ.get("AI302_KEY", "")

    if not args.non_interactive:
        if not tts_key or "your_" in tts_key:
            tts_key = prompt_secret("MiniMax/302 API key", "")
        if not image_key or "your_" in image_key:
            image_key = prompt_secret(f"{provider} API key", "")
        if not cover_key or "your_" in cover_key:
            cover_key = prompt_secret("302.AI cover key (optional; press Enter to skip)", "")

    if not tts_key or "your_" in tts_key:
        raise SystemExit("Missing MiniMax/302 API key. Pass --tts-key or run interactively.")
    if not image_key or "your_" in image_key:
        raise SystemExit(f"Missing {provider} API key. Pass --image-key or run interactively.")

    set_option(config, "TTS", "provider", "minimax")
    set_option(config, "TTS", "concurrency", "16")
    set_option(config, "MiniMax", "api_key", tts_key)
    set_option(config, "MiniMax", "api_url", args.tts_api_url)
    set_option(config, "MiniMax", "voice_id", args.tts_voice_id)
    set_option(config, "MiniMax", "title_to_srt", "")
    set_option(config, "MiniMax", "skill_dir", "")
    set_option(config, "TextToSRT", "enable_ai_split", "false")
    set_option(config, "Audio", "bgm_volume", "-28")
    set_option(config, "Paths", "default_bgm", "../../skills/whiteboard-animation/assets/bgm/relaxing-piano-for-sleeping-312507.mp3")
    set_option(config, "Advanced", "whiteboard_jobs", str(args.whiteboard_jobs))

    CONFIG_PATH.write_text("", encoding="utf-8")
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        config.write(handle)

    env_values["IMAGE_PROVIDER"] = provider
    env_values[image_key_name] = image_key
    if cover_key and "your_" not in cover_key:
        env_values["AI302_KEY"] = cover_key
    if args.image_base_url:
        base_key = {
            "apimart_image2": "APIMART_BASE_URL",
            "kie_image2": "KIE_BASE_URL",
            "t8_image2": "T8_BASE_URL",
            "macode_image2": "MACODE_BASE_URL",
        }[provider]
        env_values[base_key] = args.image_base_url
    concurrency_key = {
        "apimart_image2": "APIMART_IMAGE_CONCURRENCY",
        "kie_image2": "KIE_IMAGE_CONCURRENCY",
        "t8_image2": "T8_IMAGE_CONCURRENCY",
        "macode_image2": "MACODE_IMAGE_CONCURRENCY",
    }[provider]
    env_values[concurrency_key] = str(args.image_concurrency)
    write_env(env_values)

    print("[OK] Wrote local configuration")
    print(f"  config: {CONFIG_PATH}")
    print(f"  env:    {ENV_PATH}")
    print(f"  tts key: {mask(tts_key)}")
    print(f"  image provider: {provider}")
    print(f"  image key: {mask(image_key)}")
    print(f"  cover key: {mask(cover_key) if cover_key else '<not configured>'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
