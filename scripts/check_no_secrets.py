#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan commit-candidate text files for likely leaked API keys."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(api_key|apikey|authorization|bearer)\s*=\s*(?!your_|<|$)[A-Za-z0-9._-]{20,}"),
]
ALLOWLIST_PATTERNS = [
    re.compile(r"your_[A-Za-z0-9_]+"),
    re.compile(r"openapi/[A-Fa-f0-9]{32,}\.flac"),
]
SKIP_SUFFIXES = {
    ".flac",
    ".mp3",
    ".mp4",
    ".pdf",
    ".jfif",
    ".jpg",
    ".jpeg",
    ".png",
    ".wav",
}


def git_candidate_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO_ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_allowed(line: str) -> bool:
    return any(pattern.search(line) for pattern in ALLOWLIST_PATTERNS)


def main() -> int:
    findings: list[tuple[Path, int, str]] = []
    for path in git_candidate_files():
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if is_allowed(line):
                continue
            if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                findings.append((path, lineno, line.strip()))

    if findings:
        print("[FAILED] Possible secrets found in commit-candidate files:")
        for path, lineno, line in findings:
            rel = path.relative_to(REPO_ROOT)
            print(f"  {rel}:{lineno}: {line[:160]}")
        return 1

    print("[OK] No obvious API keys found in commit-candidate text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
