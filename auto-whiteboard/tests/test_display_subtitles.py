import configparser
import importlib.util
import os
import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


normalize = load_module("normalize_display_subtitles", "normalize_display_subtitles.py")
voiceover = load_module("generate_voiceover", "generate_voiceover.py")


class DisplaySubtitleTests(unittest.TestCase):
    def test_keeps_natural_approximation_and_multiplier(self):
        text = "当地人种了几千年，欧洲人口翻了一倍，平均每个人一年吃一次"
        self.assertEqual(normalize.normalize_display_text(text), text)

    def test_converts_scannable_numeric_information(self):
        text = "二零二五年收入一百一十四亿美元，占百分之六十一"
        self.assertEqual(normalize.normalize_display_text(text), "2025年收入114亿美元，占61%")

    def test_project_model_overrides_old_environment_default(self):
        config = configparser.ConfigParser()
        config.read_dict({"MiniMax": {"model": "speech-2.8-turbo"}})
        previous = os.environ.get("MINIMAX_TTS_MODEL")
        os.environ["MINIMAX_TTS_MODEL"] = "speech-2.6-turbo"
        try:
            value = voiceover.config_then_env(
                config,
                "MiniMax",
                "model",
                ["MINIMAX_TTS_MODEL"],
                "speech-2.8-turbo",
            )
        finally:
            if previous is None:
                os.environ.pop("MINIMAX_TTS_MODEL", None)
            else:
                os.environ["MINIMAX_TTS_MODEL"] = previous
        self.assertEqual(value, "speech-2.8-turbo")


if __name__ == "__main__":
    unittest.main()
