#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end whiteboard video generation workflow."""

import argparse
import configparser
import io
import json
import os
import subprocess
import sys
from datetime import datetime


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


def load_config(config_path):
    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8-sig")
    return config


def run_script(script_path, args_list):
    """Run a Python helper, stream output, and return its final RESULT_JSON."""
    cmd = [sys.executable, script_path] + args_list
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    print(f"\n[RUN] {os.path.basename(script_path)}")
    print(f"      args: {' '.join(args_list)}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )

        output_lines = []
        for line in process.stdout:
            output_lines.append(line)
            print(line, end="")

        returncode = process.wait()
        output = "".join(output_lines)
        if returncode != 0:
            print(f"[ERROR] Script failed with exit code {returncode}: {script_path}", file=sys.stderr)
            return False, None

        result_json_lines = []
        for line in output.splitlines():
            if line.startswith("RESULT_JSON="):
                result_json_lines.append(line.replace("RESULT_JSON=", "", 1).strip())

        if result_json_lines:
            return True, json.loads(result_json_lines[-1])

        return True, None
    except Exception as exc:
        print(f"[ERROR] Could not run script {script_path}: {exc}", file=sys.stderr)
        return False, None


def resolve_config_path(script_dir, config_arg):
    if os.path.isabs(config_arg):
        return os.path.abspath(config_arg)
    return os.path.abspath(os.path.join(script_dir, config_arg))


def main():
    parser = argparse.ArgumentParser(description="Generate a whiteboard video from a text file")
    parser.add_argument("--input", required=True, help="Input text file")
    parser.add_argument("--output-dir", help="Output root directory")
    parser.add_argument("--project-dir", help="Existing project directory to resume/reuse")
    parser.add_argument("--bgm", help="Optional background music file")
    parser.add_argument("--config", default="../config/config.ini", help="Config file path")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files for resume/debugging")
    parser.add_argument("--tts-concurrency", type=int, help="Parallel TTS jobs")
    parser.add_argument("--force-tts", action="store_true", help="Regenerate TTS even if cached segments exist")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = resolve_config_path(script_dir, args.config)
    if not os.path.exists(config_path):
        print(f"[ERROR] Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)
    output_dir = os.path.abspath(args.output_dir or config.get("Paths", "output_dir", fallback="./output"))

    if args.project_dir:
        project_dir = os.path.abspath(args.project_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = os.path.join(output_dir, f"project_{timestamp}")
    os.makedirs(project_dir, exist_ok=True)

    print("=" * 72)
    print("Whiteboard video generation")
    print("=" * 72)
    print(f"[PROJECT] {project_dir}")
    print(f"[INPUT]   {os.path.abspath(args.input)}")

    print("\n" + "=" * 72)
    print("Step 1/5: split text")
    print("=" * 72)
    sentences_path = os.path.join(project_dir, "sentences.json")
    success, result = run_script(
        os.path.join(script_dir, "text_to_srt.py"),
        ["--input", args.input, "--output", sentences_path, "--config", config_path],
    )
    if not success or not result:
        print("[ERROR] Text splitting failed", file=sys.stderr)
        sys.exit(1)

    sentence_count = result["sentence_count"]
    print(f"[OK] Text split into {sentence_count} segments")

    print("\n" + "=" * 72)
    print("Step 2/5: generate voiceover and subtitles")
    print("=" * 72)
    tts_args = ["--sentences", sentences_path, "--output-dir", project_dir, "--config", config_path]
    if args.keep_temp:
        tts_args.append("--keep-temp")
    if args.tts_concurrency:
        tts_args.extend(["--concurrency", str(args.tts_concurrency)])
    if args.force_tts:
        tts_args.append("--force-tts")

    success, result = run_script(os.path.join(script_dir, "generate_voiceover.py"), tts_args)
    if not success or not result:
        print("[ERROR] TTS voiceover generation failed", file=sys.stderr)
        sys.exit(1)

    voiceover_path = result["voiceover_path"]
    srt_path = result["srt_path"]
    total_duration = result["total_duration"]
    print(f"[OK] Voiceover: {total_duration:.2f}s")

    print("\n" + "=" * 72)
    print("Step 3/5: generate whiteboard animation")
    print("=" * 72)
    success, result = run_script(
        os.path.join(script_dir, "generate_whiteboard_video.py"),
        ["--srt", srt_path, "--output-dir", project_dir, "--config", config_path, "--skip-audio"],
    )
    if not success or not result:
        print("[ERROR] Whiteboard video generation failed", file=sys.stderr)
        sys.exit(1)
    if "whiteboard_video_path" not in result:
        print(f"[ERROR] Unexpected whiteboard result: {result}", file=sys.stderr)
        sys.exit(1)

    video_path = result["whiteboard_video_path"]
    scene_count = result.get("scene_count", 0)
    print(f"[OK] Whiteboard animation: {scene_count} scenes")

    if args.bgm:
        print("\n" + "=" * 72)
        print("Step 4/5: mix audio")
        print("=" * 72)
        mixed_audio_path = os.path.join(project_dir, "mixed_audio.wav")
        success, _ = run_script(
            os.path.join(script_dir, "audio_mixer.py"),
            [
                "--voiceover",
                voiceover_path,
                "--bgm",
                args.bgm,
                "--output",
                mixed_audio_path,
                "--config",
                config_path,
            ],
        )
        if not success:
            print("[ERROR] Audio mixing failed", file=sys.stderr)
            sys.exit(1)
        final_audio_path = mixed_audio_path
    else:
        print("\n[SKIP] Step 4/5: no background music")
        final_audio_path = voiceover_path

    print("\n" + "=" * 72)
    print("Step 5/5: compose final video")
    print("=" * 72)
    final_video_path = os.path.join(project_dir, "final_video.mp4")
    success, result = run_script(
        os.path.join(script_dir, "video_composer.py"),
        [
            "--video",
            video_path,
            "--srt",
            srt_path,
            "--audio",
            final_audio_path,
            "--output",
            final_video_path,
            "--config",
            config_path,
        ],
    )
    if not success or not result:
        print("[ERROR] Final video composition failed", file=sys.stderr)
        sys.exit(1)

    file_size = result.get("size_mb", 0)

    if not args.keep_temp:
        for temp_file in [sentences_path]:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    print("\n" + "=" * 72)
    print("Done")
    print("=" * 72)
    print(f"[OUTPUT] final video: {final_video_path}")
    print(f"[OUTPUT] subtitles:   {srt_path}")
    print(f"[OUTPUT] audio:       {final_audio_path}")
    print(f"[PROJECT] {project_dir}")
    print(f"[INFO] duration: {total_duration:.2f}s")
    print(f"[INFO] size: {file_size:.2f} MB")


if __name__ == "__main__":
    main()
