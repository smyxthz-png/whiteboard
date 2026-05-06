#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate per-sentence TTS audio, merge it, and create sync-accurate SRT."""

import argparse
import configparser
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import requests


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


RUNNINGHUB_TTS_APP_ID = "1966743528380510209"


def load_config(config_path):
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        print(f"[ERROR] Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    files_read = config.read(config_path, encoding="utf-8-sig")
    if not files_read:
        print(f"[ERROR] Could not read config file: {config_path}", file=sys.stderr)
        sys.exit(1)

    return config


def mask_secret(value):
    if not value:
        return ""
    if len(value) <= 12:
        return "<redacted>"
    return f"{value[:8]}...{value[-4:]}"


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_hash(payload):
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def tts_cache_identity(config, reference_audio, tone):
    return {
        "provider": config.get("TTS", "provider", fallback="runninghub"),
        "voice_id": config.get("TTS", "voice_id", fallback="default"),
        "reference_audio": reference_audio or "",
        "tone": tone or "",
        "app_id": RUNNINGHUB_TTS_APP_ID,
    }


def segment_cache_hash(text, identity):
    return stable_hash({
        "text": text,
        "tts_identity": identity,
    })


def get_audio_duration(audio_path):
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
                audio_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except Exception as exc:
        print(f"[WARN] Could not read audio duration for {audio_path}: {exc}", file=sys.stderr)
        return 0.0


def is_valid_audio(audio_path, min_duration=0.05):
    if not os.path.exists(audio_path):
        return False
    if os.path.getsize(audio_path) < 1024:
        return False
    return get_audio_duration(audio_path) >= min_duration


def format_srt_timestamp(seconds):
    seconds = max(0.0, seconds)
    td = timedelta(seconds=seconds)
    total = td.total_seconds()
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = int(total % 60)
    millis = int(round((total - int(total)) * 1000))
    if millis == 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def read_manifest(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception as exc:
        print(f"[WARN] Ignoring unreadable TTS manifest: {exc}", file=sys.stderr)
    return {}


def write_manifest(path, manifest):
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def load_voice_settings(config):
    voice_library_path = config.get("TTS", "voice_library", fallback="config/voice_library.json")
    voice_id = config.get("TTS", "voice_id", fallback="default")

    if not os.path.isabs(voice_library_path):
        project_root = os.path.dirname(os.path.dirname(__file__))
        voice_library_path = os.path.join(project_root, voice_library_path)

    reference_audio = None
    tone = "\u81ea\u7136"

    if os.path.exists(voice_library_path):
        try:
            with open(voice_library_path, "r", encoding="utf-8") as handle:
                voice_library = json.load(handle)

            voices = voice_library.get("voices", []) + voice_library.get("custom_voices", [])
            selected = next((voice for voice in voices if voice.get("id") == voice_id), None)
            if selected:
                reference_audio = selected.get("uploaded_file_name") or selected.get("reference_audio") or None
                tone = selected.get("tone") or tone
                print(f"[INFO] Voice: {selected.get('name', voice_id)}")
            else:
                print(f"[WARN] Voice id '{voice_id}' not found, using default TTS voice", file=sys.stderr)
        except Exception as exc:
            print(f"[WARN] Could not load voice library, using default voice: {exc}", file=sys.stderr)

    reference_audio = config.get("TTS", "reference_audio", fallback=reference_audio) or reference_audio
    tone = config.get("TTS", "tone", fallback=tone) or tone
    return reference_audio, tone


def get_api_key(config):
    api_key = config.get("RunningHubTTS", "api_key", fallback=None)
    if not api_key:
        api_key = config.get("RunningHub", "api_key", fallback="")

    if not api_key or api_key == "your_runninghub_tts_api_key_here" or api_key == "your_runninghub_key_here":
        print("[ERROR] Please configure a valid RunningHub TTS API key.", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] TTS API key: {mask_secret(api_key)}")
    return api_key


def submit_runninghub_tts(text, api_key, reference_audio, tone):
    submit_url = f"https://www.runninghub.cn/openapi/v2/run/ai-app/{RUNNINGHUB_TTS_APP_ID}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    node_info_list = [
        {
            "nodeId": "4",
            "fieldName": "prompt",
            "fieldValue": text,
            "description": "text",
        },
        {
            "nodeId": "19",
            "fieldName": "text",
            "fieldValue": tone,
            "description": "tone",
        },
    ]
    if reference_audio:
        node_info_list.append(
            {
                "nodeId": "18",
                "fieldName": "audio",
                "fieldValue": reference_audio,
                "description": "reference audio",
            }
        )

    payload = {
        "nodeInfoList": node_info_list,
        "instanceType": "default",
        "usePersonalQueue": "false",
    }
    response = requests.post(submit_url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()

    if data.get("status") not in {"QUEUED", "RUNNING"} or not data.get("taskId"):
        raise RuntimeError(f"Unexpected submit response: {data}")
    return data["taskId"]


def wait_runninghub_result(task_id, api_key, max_wait_seconds=900, poll_interval=5):
    query_url = "https://www.runninghub.cn/openapi/v2/query"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    deadline = time.monotonic() + max_wait_seconds
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        time.sleep(poll_interval)
        response = requests.post(query_url, headers=headers, json={"taskId": task_id}, timeout=30)
        response.raise_for_status()
        data = response.json()
        status = data.get("status")

        if status == "SUCCESS":
            results = data.get("results") or []
            audio_url = results[0].get("url") if results else None
            if not audio_url:
                raise RuntimeError(f"TTS task succeeded without audio URL: {data}")
            return audio_url

        if status == "FAILED":
            raise RuntimeError(data.get("errorMessage") or f"TTS task failed: {data}")

        if status not in {"QUEUED", "RUNNING"}:
            raise RuntimeError(f"Unexpected TTS task status: {data}")

        if attempt % 6 == 0:
            print(f"      waiting for task {task_id} ({attempt * poll_interval}s)")

    raise TimeoutError(f"TTS task timed out after {max_wait_seconds}s: {task_id}")


def download_audio(audio_url, output_path):
    temp_path = f"{output_path}.tmp"
    with requests.get(audio_url, stream=True, timeout=90) as response:
        response.raise_for_status()
        with open(temp_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    handle.write(chunk)

    if os.path.getsize(temp_path) < 1024:
        raise RuntimeError("Downloaded audio is too small")

    os.replace(temp_path, output_path)


def generate_tts_runninghub(text, output_path, api_key, reference_audio=None, tone="\u81ea\u7136"):
    task_id = submit_runninghub_tts(text, api_key, reference_audio, tone)
    print(f"      task id: {task_id}")
    audio_url = wait_runninghub_result(task_id, api_key)
    download_audio(audio_url, output_path)

    duration = get_audio_duration(output_path)
    if duration <= 0:
        raise RuntimeError("Generated audio has zero duration")
    return duration


def generate_one_segment(idx, sentence_text, audio_path, api_key, reference_audio, tone, retries, cache_hash):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            duration = generate_tts_runninghub(sentence_text, audio_path, api_key, reference_audio, tone)
            return {
                "index": idx,
                "audio_path": os.path.abspath(audio_path),
                "duration": duration,
                "text_hash": text_hash(sentence_text),
                "cache_hash": cache_hash,
                "text": sentence_text,
                "reused": False,
            }
        except Exception as exc:
            last_error = exc
            print(f"[WARN] Segment {idx} attempt {attempt}/{retries} failed: {exc}", file=sys.stderr)
            time.sleep(min(10, attempt * 2))

    raise RuntimeError(f"Segment {idx} failed after {retries} attempts: {last_error}")


def normalize_sentence(sentence):
    if isinstance(sentence, dict):
        return str(sentence.get("text", "")).strip()
    return str(sentence).strip()


def prepare_segments(sentences, config, output_dir, concurrency, force_tts=False):
    api_key = get_api_key(config)
    reference_audio, tone = load_voice_settings(config)
    cache_identity = tts_cache_identity(config, reference_audio, tone)
    retries = config.getint("TTS", "retries", fallback=3)

    temp_dir = os.path.join(output_dir, "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)
    manifest_path = os.path.join(temp_dir, "manifest.json")
    manifest = read_manifest(manifest_path)

    normalized = [normalize_sentence(sentence) for sentence in sentences]
    normalized = [sentence for sentence in normalized if sentence]
    total = len(normalized)
    if not total:
        raise RuntimeError("Sentence list is empty after normalization")

    print(f"\n[TTS] Generating voiceover for {total} segments")
    print(f"      concurrency: {concurrency}")
    print(f"      retries: {retries}")
    if reference_audio:
        print(f"      reference audio: {reference_audio}")
    print(f"      tone: {tone}")

    results = {}
    pending = []

    for idx, sentence_text in enumerate(normalized, start=1):
        audio_path = os.path.join(temp_dir, f"segment_{idx:03d}.mp3")
        key = str(idx)
        expected_text_hash = text_hash(sentence_text)
        expected_cache_hash = segment_cache_hash(sentence_text, cache_identity)
        manifest_entry = manifest.get(key) if isinstance(manifest.get(key), dict) else {}
        hash_matches = bool(manifest_entry) and manifest_entry.get("cache_hash") == expected_cache_hash

        if not force_tts and hash_matches and is_valid_audio(audio_path):
            duration = get_audio_duration(audio_path)
            results[idx] = {
                "index": idx,
                "audio_path": os.path.abspath(audio_path),
                "duration": duration,
                "text_hash": expected_text_hash,
                "cache_hash": expected_cache_hash,
                "text": sentence_text,
                "reused": True,
            }
            print(f"  [{idx}/{total}] reuse {os.path.basename(audio_path)} ({duration:.2f}s)")
            continue

        pending.append((idx, sentence_text, audio_path, expected_cache_hash))

    if pending:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
            futures = {
                executor.submit(
                    generate_one_segment,
                    idx,
                    sentence_text,
                    audio_path,
                    api_key,
                    reference_audio,
                    tone,
                    retries,
                    expected_cache_hash,
                ): (idx, sentence_text)
                for idx, sentence_text, audio_path, expected_cache_hash in pending
            }

            for future in as_completed(futures):
                idx, sentence_text = futures[future]
                result = future.result()
                results[idx] = result
                print(f"  [{idx}/{total}] generated ({result['duration']:.2f}s): {sentence_text[:36]}")
                manifest[str(idx)] = {
                    "text_hash": result["text_hash"],
                    "cache_hash": result["cache_hash"],
                    "tts_identity": cache_identity,
                    "text": sentence_text,
                    "audio_path": result["audio_path"],
                    "duration": result["duration"],
                }
                write_manifest(manifest_path, manifest)

    ordered = []
    missing = []
    for idx in range(1, total + 1):
        result = results.get(idx)
        if not result or not is_valid_audio(result["audio_path"]):
            missing.append(idx)
        else:
            ordered.append(result)

    if missing:
        raise RuntimeError(f"Missing or invalid TTS segments: {missing}")

    for result in ordered:
        manifest[str(result["index"])] = {
            "text_hash": result["text_hash"],
            "cache_hash": result["cache_hash"],
            "tts_identity": cache_identity,
            "text": result["text"],
            "audio_path": result["audio_path"],
            "duration": result["duration"],
        }
    write_manifest(manifest_path, manifest)
    return ordered


def build_srt(segments, pause):
    srt_lines = []
    current_time = 0.0

    for segment in segments:
        idx = segment["index"]
        text = segment["text"]
        duration = segment["duration"]
        start_time = current_time
        end_time = current_time + duration

        srt_lines.append(str(idx))
        srt_lines.append(f"{format_srt_timestamp(start_time)} --> {format_srt_timestamp(end_time)}")
        srt_lines.append(text)
        srt_lines.append("")

        current_time = end_time + pause

    total_duration = max(0.0, current_time - pause)
    return "\n".join(srt_lines), total_duration


def merge_audio_segments(segments, output_path, pause=0.5):
    if not segments:
        raise RuntimeError("No TTS segments to merge")

    print("\n[MERGE] Merging audio segments")
    inputs = []
    filter_parts = []
    for i, segment in enumerate(segments):
        inputs.extend(["-i", segment["audio_path"]])
        if i < len(segments) - 1 and pause > 0:
            filter_parts.append(f"[{i}:a]apad=pad_dur={pause}[a{i}]")
        else:
            filter_parts.append(f"[{i}:a]acopy[a{i}]")

    concat_inputs = "".join(f"[a{i}]" for i in range(len(segments)))
    filter_parts.append(f"{concat_inputs}concat=n={len(segments)}:v=0:a=1[out]")

    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[out]",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "44100",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Audio merge timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Audio merge failed: {exc.stderr}") from exc

    duration = get_audio_duration(output_path)
    print(f"      output: {output_path}")
    print(f"      duration: {duration:.2f}s")
    return duration


def main():
    parser = argparse.ArgumentParser(description="Generate TTS voiceover and sync SRT")
    parser.add_argument("--sentences", required=True, help="Sentence JSON path")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--config", default="../config/config.ini", help="Config file path")
    parser.add_argument("--pause", type=float, help="Pause between sentences in seconds")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary segment audio")
    parser.add_argument("--concurrency", type=int, help="Number of TTS jobs to run in parallel")
    parser.add_argument("--force-tts", action="store_true", help="Regenerate all TTS segments")
    args = parser.parse_args()

    if os.path.isabs(args.config):
        config_path = args.config
    else:
        project_root = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(project_root, args.config)
    config = load_config(os.path.abspath(config_path))

    pause = args.pause if args.pause is not None else config.getfloat("TextToSRT", "pause", fallback=0.5)
    concurrency = args.concurrency if args.concurrency else config.getint("TTS", "concurrency", fallback=1)
    concurrency = max(1, min(concurrency, 8))

    with open(args.sentences, "r", encoding="utf-8-sig") as handle:
        sentences = json.load(handle)

    os.makedirs(args.output_dir, exist_ok=True)

    try:
        segments = prepare_segments(sentences, config, args.output_dir, concurrency, args.force_tts)
        srt_content, expected_duration = build_srt(segments, pause)

        srt_path = os.path.join(args.output_dir, "subtitles.srt")
        with open(srt_path, "w", encoding="utf-8") as handle:
            handle.write(srt_content)

        voiceover_path = os.path.join(args.output_dir, "voiceover.wav")
        merged_duration = merge_audio_segments(segments, voiceover_path, pause)
        if abs(merged_duration - expected_duration) > 0.15:
            print(
                f"[WARN] Merged audio duration differs from SRT timeline: "
                f"audio={merged_duration:.2f}s srt={expected_duration:.2f}s",
                file=sys.stderr,
            )

        if not args.keep_temp:
            temp_dir = os.path.join(args.output_dir, "temp_audio")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print("[CLEANUP] Removed temporary segment audio")

        result = {
            "voiceover_path": os.path.abspath(voiceover_path),
            "srt_path": os.path.abspath(srt_path),
            "total_duration": merged_duration,
            "segment_count": len(segments),
        }
        print("\n[SUCCESS] Voiceover and subtitles generated")
        print(f"[OUTPUT] voiceover: {voiceover_path}")
        print(f"[OUTPUT] subtitles: {srt_path}")
        print(f"[INFO] duration: {merged_duration:.2f}s")
        print(f"\nRESULT_JSON={json.dumps(result, ensure_ascii=False)}")
    except Exception as exc:
        print(f"[ERROR] Voiceover generation failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
