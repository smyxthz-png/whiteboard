#!/usr/bin/env python3
"""Delegate a full video run to the repository's canonical pipeline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE = REPO_ROOT / "auto-whiteboard" / "scripts" / "auto_generate.py"
CONFIG = REPO_ROOT / "auto-whiteboard" / "config" / "config.ini"


def main() -> int:
    if not PIPELINE.exists():
        print(f"Video pipeline not found: {PIPELINE}", file=sys.stderr)
        return 1
    arguments = list(sys.argv[1:])
    if "--config" not in arguments:
        arguments.extend(["--config", str(CONFIG)])
    return subprocess.run([sys.executable, str(PIPELINE), *arguments], cwd=REPO_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
