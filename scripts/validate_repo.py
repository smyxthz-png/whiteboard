#!/usr/bin/env python3
"""Validate repository structure and locked production defaults without API calls."""

from __future__ import annotations

import configparser
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_EXAMPLE = REPO_ROOT / "auto-whiteboard" / "config" / "config.example.ini"
ENV_EXAMPLE = REPO_ROOT / "skills" / "whiteboard-video-workflow" / ".env.example"

REQUIRED_PATHS = (
    "README.md",
    "LICENSE",
    "ASSETS.md",
    "AGENTS.md",
    "AGENT_RUNBOOK.md",
    "scripts/bootstrap.ps1",
    "scripts/bootstrap.sh",
    "scripts/configure_keys.py",
    "scripts/doctor.py",
    "scripts/generate_cover_302.py",
    "skills/auto-whiteboard-video/SKILL.md",
    "skills/youtube-cover-generator/SKILL.md",
    "skills/whiteboard-animation/assets/drawing-hand-v2.png",
    "skills/whiteboard-animation/assets/bgm/relaxing-piano-for-sleeping-312507.mp3",
)

SKILLS = (
    "auto-whiteboard-video",
    "whiteboard-animation",
    "whiteboard-video-workflow",
    "youtube-cover-generator",
)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def validate_skill(skill_name: str) -> list[str]:
    errors: list[str] = []
    path = REPO_ROOT / "skills" / skill_name / "SKILL.md"
    if not path.exists():
        return [f"missing skill: {path.relative_to(REPO_ROOT)}"]
    text = path.read_text(encoding="utf-8-sig")
    frontmatter = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not frontmatter:
        return [f"invalid frontmatter: {path.relative_to(REPO_ROOT)}"]
    block = frontmatter.group(1)
    if f"name: {skill_name}" not in block:
        errors.append(f"skill name mismatch: {path.relative_to(REPO_ROOT)}")
    if not re.search(r"^description:\s*\S+", block, re.MULTILINE):
        errors.append(f"missing skill description: {path.relative_to(REPO_ROOT)}")
    if "TODO" in text:
        errors.append(f"unfinished TODO in skill: {path.relative_to(REPO_ROOT)}")
    return errors


def main() -> int:
    errors: list[str] = []

    for relative_path in REQUIRED_PATHS:
        if not (REPO_ROOT / relative_path).exists():
            errors.append(f"missing required path: {relative_path}")

    if CONFIG_EXAMPLE.exists():
        config = configparser.ConfigParser(interpolation=None)
        config.read(CONFIG_EXAMPLE, encoding="utf-8-sig")
        expected = {
            ("Video", "resolution"): "1920x1080",
            ("Video", "fps"): "30",
            ("Subtitle", "font_size"): "88",
            ("Subtitle", "max_chars_per_line"): "20",
            ("Audio", "bgm_volume"): "-28",
        }
        for (section, option), value in expected.items():
            actual = config.get(section, option, fallback="")
            if actual != value:
                errors.append(f"locked config changed: [{section}] {option}={actual!r}, expected {value!r}")

    if ENV_EXAMPLE.exists():
        env = read_env(ENV_EXAMPLE)
        if env.get("IMAGE_PROVIDER") != "apimart_image2":
            errors.append("IMAGE_PROVIDER default must remain apimart_image2")
        if env.get("APIMART_IMAGE_SIZE") != "1792x1008":
            errors.append("APIMART_IMAGE_SIZE must remain 1792x1008")
        if "AI302_KEY" not in env:
            errors.append(".env.example must expose optional AI302_KEY")

    for skill_name in SKILLS:
        errors.extend(validate_skill(skill_name))

    if errors:
        print("[FAILED] Repository validation errors:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("[OK] Repository structure and locked defaults are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
