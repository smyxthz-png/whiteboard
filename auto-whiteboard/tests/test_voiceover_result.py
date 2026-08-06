#!/usr/bin/env python3
"""Regression tests for segmented TTS result reporting."""

from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_voiceover.py"
COMPOSER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "video_composer.py"
DOCTOR_PATH = Path(__file__).resolve().parents[2] / "scripts" / "doctor.py"


class VoiceoverResultTests(unittest.TestCase):
    def test_segmented_branch_assigns_segment_count_before_reporting(self):
        tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
        assignments = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "segment_count" for target in node.targets)
        ]
        self.assertGreaterEqual(len(assignments), 2)

    def test_ffmpeg_ass_filter_uses_explicit_filename_option(self):
        source = COMPOSER_PATH.read_text(encoding="utf-8")
        self.assertIn("ass=filename=", source)

    def test_doctor_ffmpeg_ass_check_is_callable(self):
        spec = importlib.util.spec_from_file_location("doctor_test", DOCTOR_PATH)
        assert spec and spec.loader
        doctor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(doctor)
        result = doctor.check_ffmpeg_ass_filter()
        self.assertIn("ok", result)


if __name__ == "__main__":
    unittest.main()
