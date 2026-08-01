#!/usr/bin/env python3
"""Offline tests for the locked cover generator."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "generate_cover_302.py"
SPEC = importlib.util.spec_from_file_location("generate_cover_302", MODULE_PATH)
assert SPEC and SPEC.loader
COVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COVER)


class CoverGeneratorTests(unittest.TestCase):
    def test_youtube_preset_is_16_by_9(self):
        self.assertEqual(COVER.platform_dimensions("youtube", None, None), (1280, 720, "horizontal 16:9 video thumbnail"))

    def test_custom_dimensions_override_platform(self):
        width, height, _ = COVER.platform_dimensions("youtube", 1920, 1080)
        self.assertEqual((width, height), (1920, 1080))

    def test_prompt_contains_locked_style_and_exact_title(self):
        args = SimpleNamespace(
            title="建造文明的饮料",
            subtitle="一万年的啤酒史",
            topic="啤酒与文明",
            subject="beer glass",
            left_context="Sumerian brewery",
            right_context="modern city",
            timeline="一万年前|苏美尔|工业革命|今天",
        )
        prompt = COVER.build_prompt(args, 1280, 720, "horizontal 16:9 video thumbnail")
        self.assertIn('Exact large Chinese title: "建造文明的饮料"', prompt)
        self.assertIn("#F6F1E3", prompt)
        self.assertIn("faceless round-headed people", prompt)
        self.assertIn("No local white patches", prompt)


if __name__ == "__main__":
    unittest.main()
