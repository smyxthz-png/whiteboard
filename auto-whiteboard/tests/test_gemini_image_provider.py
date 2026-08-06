#!/usr/bin/env python3
"""Offline tests for the official Gemini image provider adapter."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "skills" / "whiteboard-video-workflow" / "scripts" / "generate-image.py"
TTS_MODULE_PATH = REPO_ROOT / "auto-whiteboard" / "scripts" / "generate_voiceover.py"
SPEC = importlib.util.spec_from_file_location("generate_image", MODULE_PATH)
assert SPEC and SPEC.loader
GENERATE_IMAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATE_IMAGE)
TTS_SPEC = importlib.util.spec_from_file_location("generate_voiceover_gemini_test", TTS_MODULE_PATH)
assert TTS_SPEC and TTS_SPEC.loader
TTS = importlib.util.module_from_spec(TTS_SPEC)
TTS_SPEC.loader.exec_module(TTS)


class GeminiImageProviderTests(unittest.TestCase):
    def test_provider_aliases_normalize_to_gemini_image(self):
        for alias in ("gemini", "gemini_image", "google", "google_gemini"):
            with self.subTest(alias=alias), patch.dict(os.environ, {"IMAGE_PROVIDER": alias}):
                self.assertEqual(GENERATE_IMAGE.get_image_provider(), "gemini_image")

    def test_extracts_last_non_thinking_image(self):
        response = {
            "candidates": [{
                "content": {"parts": [
                    {"thought": True, "inlineData": {"mimeType": "image/png", "data": "draft"}},
                    {"inlineData": {"mimeType": "image/png", "data": "final"}},
                ]}
            }]
        }
        self.assertEqual(GENERATE_IMAGE.extract_gemini_image(response), "final")

    def test_image_config_preserves_aspect_ratio_and_uppercase_size(self):
        with patch.dict(os.environ, {"GEMINI_IMAGE_SIZE": "2k"}):
            self.assertEqual(
                GENERATE_IMAGE.gemini_image_config("16:9"),
                {"aspectRatio": "16:9", "imageSize": "2K"},
            )

    def test_extracts_gemini_audio(self):
        response = {
            "candidates": [{"content": {"parts": [{
                "inlineData": {"mimeType": "audio/L16;rate=24000", "data": "cGNt"}
            }]}}]
        }
        self.assertEqual(TTS.extract_gemini_audio(response), "cGNt")

    def test_tts_provider_alias_normalizes(self):
        import configparser

        config = configparser.ConfigParser()
        config.read_dict({"TTS": {"provider": "gemini"}})
        self.assertEqual(TTS.get_tts_provider(config), "gemini")


class ImageFailureBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_fatal_provider_error_is_not_retried(self):
        task = {"prompt": "test", "aspectRatio": "16:9", "outputDir": "/tmp", "index": 0, "total": 1}
        with patch.object(
            GENERATE_IMAGE,
            "generate_single",
            side_effect=GENERATE_IMAGE.FatalError("unsupported location"),
        ) as generate:
            results = await GENERATE_IMAGE.run_batch([task], concurrency=1)
        self.assertEqual(generate.call_count, 1)
        self.assertTrue(results[0]["fatal"])


if __name__ == "__main__":
    unittest.main()
