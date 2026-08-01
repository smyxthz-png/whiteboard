#!/usr/bin/env python3
"""Create and validate the isolated whiteboard-rendering environment."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
VENV_DIR = SKILL_DIR / ".venv"
REQUIRED_PACKAGES = {
    "cv2": "opencv-python",
    "numpy": "numpy",
    "av": "av",
}


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def package_available(python_path: Path, import_name: str) -> bool:
    result = subprocess.run(
        [str(python_path), "-c", f"import {import_name}"],
        capture_output=True,
    )
    return result.returncode == 0


def install_packages(python_path: Path, packages: list[str]) -> None:
    print(f"[..] Installing animation dependencies: {', '.join(packages)}")
    subprocess.run(
        [str(python_path), "-m", "pip", "install", "--quiet", *packages],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the whiteboard animation virtual environment")
    parser.add_argument("--check", action="store_true", help="Validate only; do not create or install")
    args = parser.parse_args()

    python_path = venv_python()
    if not python_path.exists():
        if args.check:
            print(f"[FAILED] Animation environment is missing: {VENV_DIR}")
            return 1
        print(f"[..] Creating animation environment: {VENV_DIR}")
        venv.create(str(VENV_DIR), with_pip=True)

    missing: list[str] = []
    for import_name, pip_name in REQUIRED_PACKAGES.items():
        if package_available(python_path, import_name):
            print(f"[OK] {pip_name}")
        else:
            print(f"[MISSING] {pip_name}")
            missing.append(pip_name)

    if missing and args.check:
        return 1
    if missing:
        try:
            install_packages(python_path, missing)
        except subprocess.CalledProcessError as exc:
            print(f"[FAILED] Could not install animation dependencies: {exc}", file=sys.stderr)
            return 1

    print(f"PYTHON_PATH={python_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
