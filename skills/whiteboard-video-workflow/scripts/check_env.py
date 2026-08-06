#!/usr/bin/env python3
"""Preflight checks for the whiteboard video workflow."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SKILLS_ROOT = SKILL_DIR.parent
ANIMATION_SKILL = SKILLS_ROOT / "whiteboard-animation"

PROVIDER_KEY_NAMES = {
    "runninghub": "RUNNINGHUB_API_KEY",
    "apimart": "APIMART_API_KEY",
    "apimart_image2": "APIMART_API_KEY",
    "kie": "KIE_API_KEY",
    "kie_image2": "KIE_API_KEY",
    "t8": "T8_API_KEY",
    "t8_image2": "T8_API_KEY",
    "t8star": "T8_API_KEY",
    "macode": "MACODE_API_KEY",
    "macode_image2": "MACODE_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "gemini_image": "GEMINI_API_KEY",
}


def read_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def configured_value(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    return bool(normalized) and "your_" not in normalized.lower()


def check_python_venv(check_only: bool) -> dict:
    setup_script = ANIMATION_SKILL / "scripts" / "setup_env.py"
    if not setup_script.exists():
        return {"ok": False, "error": f"setup_env.py not found: {setup_script}"}

    result = subprocess.run(
        [sys.executable, str(setup_script), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    python_path = None
    for line in result.stdout.strip().splitlines():
        if line.startswith("PYTHON_PATH="):
            python_path = line.split("=", 1)[1]

    if result.returncode == 0 and python_path:
        return {"ok": True, "pythonPath": python_path}

    if not check_only:
        print("[..] Python dependencies missing, installing...")
        install_result = subprocess.run(
            [sys.executable, str(setup_script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if install_result.returncode == 0:
            return check_python_venv(True)
        return {"ok": False, "error": "Python environment setup failed. Run setup_env.py manually."}

    return {"ok": False, "error": "Python environment is missing dependencies."}


def check_api_key() -> dict:
    env_file = SKILL_DIR / ".env"
    if not env_file.exists():
        return {"ok": False, "error": f".env file not found: {env_file}"}

    values = read_env_file(env_file)
    provider = values.get("IMAGE_PROVIDER", "runninghub").strip().lower() or "runninghub"
    key_name = PROVIDER_KEY_NAMES.get(provider)
    if not key_name:
        supported = ", ".join(sorted(PROVIDER_KEY_NAMES))
        return {"ok": False, "provider": provider, "error": f"Unsupported IMAGE_PROVIDER. Supported: {supported}"}

    if configured_value(os.environ.get(key_name) or values.get(key_name)):
        return {"ok": True, "provider": provider, "keyName": key_name}

    return {"ok": False, "provider": provider, "keyName": key_name, "error": f"{key_name} is not set in {env_file}"}


def main() -> int:
    check_only = "--check-only" in sys.argv

    results: dict[str, dict] = {}
    print("[CHECK] Python virtual environment...")
    results["python"] = check_python_venv(check_only)

    print("[CHECK] image provider API key...")
    results["apiKey"] = check_api_key()

    all_ok = all(result.get("ok") for result in results.values())
    output = {"allOk": all_ok, "checks": results}

    if all_ok:
        print("\n[OK] All environment checks passed")
        print(f"PYTHON_PATH={results['python']['pythonPath']}")
    else:
        print("\n[FAILED] Some checks failed")
        for name, result in results.items():
            status = "OK" if result.get("ok") else f"FAILED - {result.get('error', 'Unknown error')}"
            print(f"  {name}: {status}")

    print(f"\nENV_RESULT={json.dumps(output, ensure_ascii=False)}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
