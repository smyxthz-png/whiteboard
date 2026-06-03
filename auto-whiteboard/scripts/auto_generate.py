#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end whiteboard video generation workflow."""

import argparse
import configparser
import hashlib
import io
import json
import os
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path


WORKFLOW_VERSION = "2026-06-04-minimax-tts-v1"


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


def load_config(config_path):
    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8-sig")
    return config


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(path):
    if not path:
        return None
    abs_path = os.path.abspath(path)
    return {
        "path": abs_path,
        "sha256": sha256_file(abs_path),
    }


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except Exception:
        return default


def write_json_atomic(path, payload):
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def load_run_state(project_dir):
    return read_json(os.path.join(project_dir, "run_state.json"), default={}) or {}


def save_run_state(project_dir, state):
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json_atomic(os.path.join(project_dir, "run_state.json"), state)


def update_step(project_dir, state, name, status, **fields):
    steps = state.setdefault("steps", {})
    step = steps.setdefault(name, {})
    step.update(fields)
    step["status"] = status
    step["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_run_state(project_dir, state)


def valid_file(path, min_bytes=1):
    return bool(path) and os.path.exists(path) and os.path.getsize(path) >= min_bytes


def valid_json_list(path):
    data = read_json(path)
    return isinstance(data, list) and len(data) > 0


def media_duration(path):
    if not valid_file(path, 1024):
        return 0.0
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def valid_media(path):
    return valid_file(path, 1024) and media_duration(path) > 0.05


def latest_whiteboard_video(project_dir):
    candidates = sorted(Path(project_dir).glob("whiteboard_*.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if valid_media(str(candidate)):
            return str(candidate)
    return None


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


SUPPORTED_BGM_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
}


def resolve_bgm_path(bgm_arg):
    if not bgm_arg:
        return None

    bgm_path = os.path.abspath(bgm_arg)
    if not os.path.exists(bgm_path):
        print(f"[ERROR] Background music file not found: {bgm_path}", file=sys.stderr)
        sys.exit(1)

    if os.path.isfile(bgm_path):
        return bgm_path

    if not os.path.isdir(bgm_path):
        print(f"[ERROR] Background music path is not a file or directory: {bgm_path}", file=sys.stderr)
        sys.exit(1)

    candidates = [
        str(path)
        for path in Path(bgm_path).iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_BGM_EXTENSIONS
    ]
    if not candidates:
        supported = ", ".join(sorted(SUPPORTED_BGM_EXTENSIONS))
        print(f"[ERROR] No supported BGM files found in {bgm_path}. Supported: {supported}", file=sys.stderr)
        sys.exit(1)

    return random.choice(sorted(candidates))


def main():
    parser = argparse.ArgumentParser(description="Generate a whiteboard video from a text file")
    parser.add_argument("--input", required=True, help="Input text file")
    parser.add_argument("--output-dir", help="Output root directory")
    parser.add_argument("--project-dir", help="Existing project directory to resume/reuse")
    parser.add_argument("--bgm", help="Optional background music file or directory to pick from randomly")
    parser.add_argument("--config", default="../config/config.ini", help="Config file path")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files for resume/debugging")
    parser.add_argument("--tts-concurrency", type=int, help="Parallel TTS jobs")
    parser.add_argument("--force-tts", action="store_true", help="Regenerate TTS even if cached segments exist")
    parser.add_argument("--force-split", action="store_true", help="Regenerate sentence split even when cached")
    parser.add_argument("--force-images", action="store_true", help="Regenerate whiteboard source images")
    parser.add_argument("--force-whiteboard", action="store_true", help="Regenerate whiteboard animation")
    parser.add_argument("--force-compose", action="store_true", help="Regenerate final composed video")
    parser.add_argument("--whiteboard-fps", type=int, help="Override whiteboard animation FPS")
    parser.add_argument("--whiteboard-jobs", type=int, help="Override parallel whiteboard render jobs")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = resolve_config_path(script_dir, args.config)
    if not os.path.exists(config_path):
        print(f"[ERROR] Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    selected_bgm_path = resolve_bgm_path(args.bgm)

    config = load_config(config_path)
    output_dir = os.path.abspath(args.output_dir or config.get("Paths", "output_dir", fallback="./output"))

    if args.project_dir:
        project_dir = os.path.abspath(args.project_dir)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = os.path.join(output_dir, f"project_{timestamp}")
    os.makedirs(project_dir, exist_ok=True)
    state = load_run_state(project_dir)
    fingerprint = {
        "workflow_version": WORKFLOW_VERSION,
        "input_path": os.path.abspath(args.input),
        "input_sha256": sha256_file(args.input),
        "config_path": config_path,
        "config_sha256": sha256_file(config_path),
        "bgm": file_identity(selected_bgm_path),
        "whiteboard_overrides": {
            "fps": args.whiteboard_fps,
            "jobs": args.whiteboard_jobs,
        },
    }
    same_fingerprint = state.get("fingerprint") == fingerprint
    if not same_fingerprint:
        state = {"fingerprint": fingerprint, "steps": {}}
        save_run_state(project_dir, state)

    print("=" * 72)
    print("Whiteboard video generation")
    print("=" * 72)
    print(f"[PROJECT] {project_dir}")
    print(f"[INPUT]   {os.path.abspath(args.input)}")
    if selected_bgm_path:
        print(f"[BGM]     {selected_bgm_path}")

    print("\n" + "=" * 72)
    print("Step 1/5: split text")
    print("=" * 72)
    sentences_path = os.path.join(project_dir, "sentences.json")
    if same_fingerprint and not args.force_split and valid_json_list(sentences_path):
        sentences = read_json(sentences_path, default=[])
        result = {"sentences_path": os.path.abspath(sentences_path), "sentence_count": len(sentences)}
        print(f"[REUSE] Existing sentence split: {len(sentences)} segments")
    else:
        update_step(project_dir, state, "split_text", "running", output=sentences_path)
        success, result = run_script(
            os.path.join(script_dir, "text_to_srt.py"),
            ["--input", args.input, "--output", sentences_path, "--config", config_path],
        )
        if not success or not result:
            update_step(project_dir, state, "split_text", "failed")
            print("[ERROR] Text splitting failed", file=sys.stderr)
            sys.exit(1)
    update_step(project_dir, state, "split_text", "completed", result=result)

    sentence_count = result["sentence_count"]
    print(f"[OK] Text split into {sentence_count} segments")

    print("\n" + "=" * 72)
    print("Step 2/5: generate voiceover and subtitles")
    print("=" * 72)
    tts_args = [
        "--sentences",
        sentences_path,
        "--output-dir",
        project_dir,
        "--config",
        config_path,
        "--source-text",
        args.input,
    ]
    if args.keep_temp:
        tts_args.append("--keep-temp")
    if args.tts_concurrency:
        tts_args.extend(["--concurrency", str(args.tts_concurrency)])
    if args.force_tts:
        tts_args.append("--force-tts")

    voiceover_path = os.path.join(project_dir, "voiceover.wav")
    srt_path = os.path.join(project_dir, "subtitles.srt")
    if same_fingerprint and not args.force_tts and valid_media(voiceover_path) and valid_file(srt_path, 100):
        total_duration = media_duration(voiceover_path)
        result = {
            "voiceover_path": os.path.abspath(voiceover_path),
            "srt_path": os.path.abspath(srt_path),
            "total_duration": total_duration,
        }
        print(f"[REUSE] Existing voiceover and subtitles: {total_duration:.2f}s")
    else:
        update_step(project_dir, state, "tts", "running", output_dir=project_dir)
        success, result = run_script(os.path.join(script_dir, "generate_voiceover.py"), tts_args)
        if not success or not result:
            update_step(project_dir, state, "tts", "failed")
            print("[ERROR] TTS voiceover generation failed", file=sys.stderr)
            sys.exit(1)
    update_step(project_dir, state, "tts", "completed", result=result)

    voiceover_path = result["voiceover_path"]
    srt_path = result["srt_path"]
    total_duration = result["total_duration"]
    print(f"[OK] Voiceover: {total_duration:.2f}s")

    print("\n" + "=" * 72)
    print("Step 3/5: generate whiteboard animation")
    print("=" * 72)
    whiteboard_result = state.get("steps", {}).get("whiteboard", {}).get("result", {}) if same_fingerprint else {}
    reusable_whiteboard = whiteboard_result.get("whiteboard_video_path") or latest_whiteboard_video(project_dir)
    if same_fingerprint and not args.force_whiteboard and not args.force_images and valid_media(reusable_whiteboard):
        result = {
            "whiteboard_video_path": os.path.abspath(reusable_whiteboard),
            "scene_count": whiteboard_result.get("scene_count", 0),
            "image_count": whiteboard_result.get("image_count", 0),
            "video_segments": whiteboard_result.get("video_segments", 0),
        }
        print(f"[REUSE] Existing whiteboard animation: {reusable_whiteboard}")
    else:
        update_step(project_dir, state, "whiteboard", "running", output_dir=project_dir)
        whiteboard_args = ["--srt", srt_path, "--output-dir", project_dir, "--config", config_path, "--skip-audio"]
        if args.whiteboard_fps:
            whiteboard_args.extend(["--fps", str(args.whiteboard_fps)])
        if args.whiteboard_jobs:
            whiteboard_args.extend(["--jobs", str(args.whiteboard_jobs)])
        if args.force_images:
            whiteboard_args.append("--force-images")
        if args.force_whiteboard:
            whiteboard_args.append("--force-video-segments")
        success, result = run_script(os.path.join(script_dir, "generate_whiteboard_video.py"), whiteboard_args)
        if not success or not result:
            update_step(project_dir, state, "whiteboard", "failed")
            print("[ERROR] Whiteboard video generation failed", file=sys.stderr)
            sys.exit(1)
        if "whiteboard_video_path" not in result:
            update_step(project_dir, state, "whiteboard", "failed", result=result)
            print(f"[ERROR] Unexpected whiteboard result: {result}", file=sys.stderr)
            sys.exit(1)
    update_step(project_dir, state, "whiteboard", "completed", result=result)

    video_path = result["whiteboard_video_path"]
    scene_count = result.get("scene_count", 0)
    print(f"[OK] Whiteboard animation: {scene_count} scenes")

    if selected_bgm_path:
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
                selected_bgm_path,
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
    composition_report_path = os.path.join(project_dir, "composition_report.json")
    if (
        same_fingerprint
        and not args.force_compose
        and valid_media(final_video_path)
        and valid_file(composition_report_path, 100)
    ):
        result = {
            "final_video_path": os.path.abspath(final_video_path),
            "size_mb": os.path.getsize(final_video_path) / (1024 * 1024),
            "report_path": composition_report_path,
        }
        print(f"[REUSE] Existing final video: {final_video_path}")
    else:
        update_step(project_dir, state, "compose", "running", output=final_video_path)
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
            update_step(project_dir, state, "compose", "failed")
            print("[ERROR] Final video composition failed", file=sys.stderr)
            sys.exit(1)
    update_step(project_dir, state, "compose", "completed", result=result)

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
    final_result = {
        "project_dir": os.path.abspath(project_dir),
        "final_video_path": os.path.abspath(final_video_path),
        "srt_path": os.path.abspath(srt_path),
        "audio_path": os.path.abspath(final_audio_path),
        "size_mb": file_size,
        "duration": total_duration,
        "run_state_path": os.path.abspath(os.path.join(project_dir, "run_state.json")),
        "composition_report_path": os.path.abspath(composition_report_path),
    }
    print(f"\nRESULT_JSON={json.dumps(final_result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
