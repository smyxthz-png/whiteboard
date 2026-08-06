#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Environment checks for the whiteboard video workflow."""

from __future__ import annotations

import argparse
import configparser
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "auto-whiteboard" / "config" / "config.ini"
ENV_PATH = REPO_ROOT / "skills" / "whiteboard-video-workflow" / ".env"
ANIMATION_SETUP = REPO_ROOT / "skills" / "whiteboard-animation" / "scripts" / "setup_env.py"
PLACEHOLDER_MARKERS = ("your_", "YOUR_", "<", "api_key_here")


def is_real_value(value: str | None) -> bool:
    if not value:
        return False
    stripped = value.strip()
    if not stripped:
        return False
    return not any(marker in stripped for marker in PLACEHOLDER_MARKERS)


def check_command(command: str) -> dict:
    path = shutil.which(command)
    if not path:
        return {"ok": False, "error": f"{command} not found in PATH"}
    return {"ok": True, "path": path}


def check_python_packages() -> dict:
    packages = ["requests", "anthropic", "pydub"]
    missing = []
    for package in packages:
        result = subprocess.run([sys.executable, "-c", f"import {package}"], capture_output=True)
        if result.returncode != 0:
            missing.append(package)
    return {"ok": not missing, "missing": missing}


def check_cover_tool(require_key: bool = False) -> dict:
    executable_name = "302ai.exe" if os.name == "nt" else "302ai"
    local_executable = REPO_ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / executable_name
    executable = str(local_executable) if local_executable.exists() else shutil.which("302ai")
    try:
        version = importlib.metadata.version("cli-302ai")
    except importlib.metadata.PackageNotFoundError:
        version = ""
    values = load_env()
    key_configured = is_real_value(os.environ.get("AI302_KEY") or values.get("AI302_KEY"))
    return {
        "ok": bool(executable and version) and (key_configured or not require_key),
        "executable": executable or "",
        "version": version,
        "key_configured": key_configured,
        "key_required": require_key,
    }


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"ok": False, "error": f"Missing {CONFIG_PATH}"}
    config = configparser.ConfigParser(interpolation=None)
    config.read(CONFIG_PATH, encoding="utf-8-sig")
    tts_provider = config.get("TTS", "provider", fallback="")
    minimax_key = config.get("MiniMax", "api_key", fallback="")
    gemini_key = os.environ.get("GEMINI_API_KEY") or config.get("Gemini", "api_key", fallback="")
    default_bgm = config.get("Paths", "default_bgm", fallback="")
    bgm_ok = True
    bgm_path = ""
    if default_bgm:
        candidate = Path(os.path.expandvars(os.path.expanduser(default_bgm)))
        if not candidate.is_absolute():
            candidate = (CONFIG_PATH.parent / candidate).resolve()
        bgm_path = str(candidate)
        bgm_ok = candidate.exists()
    return {
        "ok": (
            (tts_provider == "minimax" and is_real_value(minimax_key))
            or (tts_provider == "gemini" and is_real_value(gemini_key))
        ) and bgm_ok,
        "tts_provider": tts_provider,
        "minimax_key_configured": is_real_value(minimax_key),
        "gemini_key_configured": is_real_value(gemini_key),
        "default_bgm": bgm_path,
        "default_bgm_exists": bgm_ok,
    }


def check_image_env() -> dict:
    if not ENV_PATH.exists():
        return {"ok": False, "error": f"Missing {ENV_PATH}"}
    values = load_env()
    provider = values.get("IMAGE_PROVIDER", "")
    key_by_provider = {
        "apimart_image2": "APIMART_API_KEY",
        "kie_image2": "KIE_API_KEY",
        "t8_image2": "T8_API_KEY",
        "macode_image2": "MACODE_API_KEY",
        "runninghub": "RUNNINGHUB_API_KEY",
        "gemini_image": "GEMINI_API_KEY",
    }
    key_name = key_by_provider.get(provider)
    key_value = os.environ.get(key_name or "", "") or values.get(key_name or "", "")
    return {
        "ok": bool(key_name) and is_real_value(key_value),
        "provider": provider,
        "key_name": key_name,
        "key_configured": is_real_value(key_value),
    }


def check_animation_env() -> dict:
    if not ANIMATION_SETUP.exists():
        return {"ok": False, "error": f"Missing {ANIMATION_SETUP}"}
    result = subprocess.run(
        [sys.executable, str(ANIMATION_SETUP), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "ok": result.returncode == 0,
        "stdout_tail": "\n".join(result.stdout.splitlines()[-5:]),
        "stderr_tail": "\n".join(result.stderr.splitlines()[-5:]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local environment without making API calls")
    parser.add_argument("--json", action="store_true", help="Print compact JSON only")
    parser.add_argument("--require-cover", action="store_true", help="Also require AI302_KEY for cover generation")
    args = parser.parse_args()

    checks = {
        "python_version": {
            "ok": (3, 11) <= sys.version_info < (3, 13),
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "expected": "Python 3.11 or 3.12",
        },
        "ffmpeg": check_command("ffmpeg"),
        "ffprobe": check_command("ffprobe"),
        "python_packages": check_python_packages(),
        "config": check_config(),
        "image_env": check_image_env(),
        "animation_env": check_animation_env(),
        "cover_tool": check_cover_tool(args.require_cover),
    }
    all_ok = all(check.get("ok") for check in checks.values())
    result = {"ok": all_ok, "checks": checks}

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("Whiteboard workflow doctor")
        print("=" * 32)
        for name, check in checks.items():
            status = "OK" if check.get("ok") else "FAILED"
            print(f"{name}: {status}")
            if not check.get("ok"):
                print(f"  {json.dumps(check, ensure_ascii=False)}")
        print("=" * 32)
        print("READY" if all_ok else "NOT READY")
        print(f"DOCTOR_JSON={json.dumps(result, ensure_ascii=False)}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
