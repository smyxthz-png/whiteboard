#!/usr/bin/env python3
"""Scan tracked text files for likely secrets and machine-specific paths."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    "assigned credential": re.compile(
        r"(?i)(api_key|apikey|authorization|bearer|token)\s*[:=]\s*(?!your_|<|\$|%|\{)[A-Za-z0-9._-]{20,}"
    ),
    "Windows home path": re.compile(r"(?i)[A-Z]:[\\/]Users[\\/][^\\/\s]+"),
    "legacy absolute project path": re.compile(r"(?i)[A-Z]:[\\/](whiteboard|xwechat_files)[\\/]"),
}
ALLOWLIST = (
    re.compile(r"your_[A-Za-z0-9_]+"),
    re.compile(r"openapi/[A-Fa-f0-9]{32,}\.flac"),
    re.compile(r"https?://"),
)
SKIP_SUFFIXES = {".flac", ".mp3", ".mp4", ".pdf", ".jfif", ".jpg", ".jpeg", ".png", ".wav"}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    return [REPO_ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def main() -> int:
    findings: list[tuple[Path, int, str, int]] = []
    for path in tracked_files():
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(content.splitlines(), 1):
            if any(pattern.search(line) for pattern in ALLOWLIST):
                continue
            for label, pattern in PATTERNS.items():
                match = pattern.search(line)
                if match:
                    findings.append((path, line_number, label, len(match.group(0))))

    if findings:
        print("[FAILED] Potential secrets or non-portable paths found:")
        for path, line_number, label, match_length in findings:
            print(f"  {path.relative_to(REPO_ROOT)}:{line_number}: {label} ({match_length} chars)")
        return 1

    print("[OK] No obvious secrets or machine-specific paths found in tracked text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
