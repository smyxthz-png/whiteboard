#!/usr/bin/env python3
"""Delegate cover generation to the repository's canonical implementation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATOR = REPO_ROOT / "scripts" / "generate_cover_302.py"


def main() -> int:
    if not GENERATOR.exists():
        print(f"Cover generator not found: {GENERATOR}", file=sys.stderr)
        return 1
    result = subprocess.run([sys.executable, str(GENERATOR), *sys.argv[1:]], cwd=REPO_ROOT)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
