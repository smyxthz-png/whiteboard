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

try:
    from clean_script_for_tts import clean_sentences as clean_tts_sentences
except Exception as exc:  # pragma: no cover - cleanup can still be skipped
    clean_tts_sentences = None
    CLEAN_TTS_IMPORT_ERROR = exc


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


RUNNINGHUB_TTS_APP_ID = "1966743528380510209"


def load_config(config_path):
    config = configparser.ConfigParser(interpolation=None)
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


def get_tts_provider(config):
    provider = (os.environ.get("TTS_PROVIDER") or config.get("TTS", "provider", fallback="runninghub")).strip().lower()
    if provider in {"fish", "fish_audio", "fishaudio"}:
        return "fish"
    if provider in {"302", "302ai", "index_tts2", "index-tts2", "302_index_tts2", "302-index-tts2"}:
        return "index_tts2"
    return "runninghub"


def config_env(config, section, option, env_names, fallback=""):
    for env_name in env_names:
        value = os.environ.get(env_name)
        if value:
            return value
    return config.get(section, option, fallback=fallback)


def parse_bool(value, fallback=False):
    if value is None or value == "":
        return fallback
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_optional_float(value):
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def parse_emotion_vector(value):
    if not value:
        return None
    if isinstance(value, list):
        vector = [float(item) for item in value]
    else:
        vector = [float(item.strip()) for item in str(value).replace("，", ",").split(",") if item.strip()]
    if len(vector) != 8:
        raise ValueError("IndexTTS2 emotion_vector must contain exactly 8 numbers")
    return vector


def should_clean_tts_text(config):
    return parse_bool(config.get("TTS", "clean_for_tts", fallback="true"), True)


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_hash(payload):
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def normalize_sentence_record(sentence):
    if isinstance(sentence, dict):
        original_text = str(
            sentence.get("original_text")
            or sentence.get("subtitle_text")
            or sentence.get("text")
            or ""
        ).strip()
        subtitle_text = str(
            sentence.get("subtitle_text")
            or sentence.get("text")
            or original_text
        ).strip()
        if "tts_text" in sentence:
            tts_text = str(sentence.get("tts_text") or "").strip()
        else:
            tts_text = str(
                sentence.get("cleaned_text")
                or sentence.get("text")
                or original_text
            ).strip()
        record = sentence.copy()
    else:
        original_text = str(sentence or "").strip()
        subtitle_text = original_text
        tts_text = original_text
        record = {}

    if not original_text and not subtitle_text and not tts_text:
        return None
    if not tts_text:
        return None

    record["text"] = original_text or tts_text
    record["original_text"] = original_text or tts_text
    record["subtitle_text"] = subtitle_text or original_text or tts_text
    record["tts_text"] = tts_text
    return record


def normalize_sentence_records(sentences):
    records = []
    for sentence in sentences:
        record = normalize_sentence_record(sentence)
        if record:
            records.append(record)
    return records


def prepare_tts_sentence_records(sentences, config, output_dir=None, skip_clean=False):
    records = normalize_sentence_records(sentences)
    if not records:
        raise RuntimeError("Sentence list is empty after normalization")

    if skip_clean or not should_clean_tts_text(config):
        print("[CLEAN] TTS cleanup disabled; using original text", file=sys.stderr)
        return records

    if clean_tts_sentences is None:
        print(
            f"[WARN] TTS cleanup module unavailable ({CLEAN_TTS_IMPORT_ERROR}); using original text",
            file=sys.stderr,
        )
        return records

    cleaned_records = clean_tts_sentences(records, config)
    if output_dir:
        cleaned_path = os.path.join(output_dir, "tts_sentences.json")
        with open(cleaned_path, "w", encoding="utf-8") as handle:
            json.dump(cleaned_records, handle, ensure_ascii=False, indent=2)
        print(f"[CLEAN] Saved cleaned sentence records: {cleaned_path}")
    return cleaned_records


def tts_cache_identity(config, reference_audio, tone):
    provider = get_tts_provider(config)
    if provider == "fish":
        return {
            "provider": provider,
            "model": config.get("FishAudio", "model", fallback=os.environ.get("FISH_AUDIO_MODEL", "s2-pro")),
            "reference_id": config.get("FishAudio", "reference_id", fallback=os.environ.get("FISH_AUDIO_REFERENCE_ID", "")),
            "latency": config.get("FishAudio", "latency", fallback="normal"),
            "format": config.get("FishAudio", "format", fallback="mp3"),
        }
    if provider == "index_tts2":
        return {
            "provider": provider,
            "base_url": config_env(config, "IndexTTS2", "base_url", ["INDEX_TTS2_BASE_URL", "AI302_BASE_URL"], "https://api.302.ai").rstrip("/"),
            "speaker_audio_url": config_env(config, "IndexTTS2", "speaker_audio_url", ["INDEX_TTS2_SPEAKER_AUDIO_URL", "AI302_SPEAKER_AUDIO_URL"], ""),
            "emotion_audio_url": config_env(config, "IndexTTS2", "emotion_audio_url", ["INDEX_TTS2_EMOTION_AUDIO_URL", "AI302_EMOTION_AUDIO_URL"], ""),
            "emotion_alpha": config_env(config, "IndexTTS2", "emotion_alpha", ["INDEX_TTS2_EMOTION_ALPHA"], ""),
            "emotion_vector": config_env(config, "IndexTTS2", "emotion_vector", ["INDEX_TTS2_EMOTION_VECTOR"], ""),
            "use_emotion_text": config_env(config, "IndexTTS2", "use_emotion_text", ["INDEX_TTS2_USE_EMOTION_TEXT"], ""),
            "emotion_text": config_env(config, "IndexTTS2", "emotion_text", ["INDEX_TTS2_EMOTION_TEXT"], ""),
        }

    return {
        "provider": provider,
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
    temp_path = f"{path}.{os.getpid()}.{time.time_ns()}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)

    last_exc = None
    for attempt in range(6):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(0.1 * (attempt + 1))

    try:
        os.remove(temp_path)
    except OSError:
        pass
    raise last_exc


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


def load_fish_settings(config):
    api_key = (
        os.environ.get("FISH_AUDIO_API_KEY")
        or os.environ.get("FISH_API_KEY")
        or config.get("FishAudio", "api_key", fallback="")
    )
    reference_id = (
        os.environ.get("FISH_AUDIO_REFERENCE_ID")
        or os.environ.get("FISH_REFERENCE_ID")
        or config.get("FishAudio", "reference_id", fallback="")
    )
    if not api_key or api_key == "your_fish_audio_api_key_here":
        print("[ERROR] Please configure a valid Fish Audio API key.", file=sys.stderr)
        sys.exit(1)
    if not reference_id or reference_id == "your_fish_reference_id_here":
        print("[ERROR] Please configure a valid Fish Audio reference_id.", file=sys.stderr)
        sys.exit(1)

    base_url = (
        os.environ.get("FISH_AUDIO_BASE_URL")
        or config.get("FishAudio", "base_url", fallback="https://api.fish.audio/v1")
    ).rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"

    settings = {
        "provider": "fish",
        "api_key": api_key,
        "base_url": base_url,
        "model": os.environ.get("FISH_AUDIO_MODEL") or config.get("FishAudio", "model", fallback="s2-pro"),
        "reference_id": reference_id,
        "format": config.get("FishAudio", "format", fallback="mp3"),
        "latency": config.get("FishAudio", "latency", fallback="normal"),
        "timeout": config.getint("FishAudio", "timeout", fallback=180),
    }
    print(f"[INFO] Fish Audio API key: {mask_secret(api_key)}")
    print(f"[INFO] Fish model: {settings['model']}")
    print(f"[INFO] Fish reference_id: {settings['reference_id']}")
    return settings


def load_index_tts2_settings(config):
    api_key = config_env(
        config,
        "IndexTTS2",
        "api_key",
        ["INDEX_TTS2_API_KEY", "AI302_API_KEY", "TTS_302_API_KEY"],
        "",
    )
    speaker_audio_url = config_env(
        config,
        "IndexTTS2",
        "speaker_audio_url",
        ["INDEX_TTS2_SPEAKER_AUDIO_URL", "AI302_SPEAKER_AUDIO_URL"],
        "",
    )
    if not api_key or api_key == "your_302_api_key_here":
        print("[ERROR] Please configure a valid 302.ai IndexTTS2 API key.", file=sys.stderr)
        sys.exit(1)
    if not speaker_audio_url or speaker_audio_url == "your_speaker_audio_url_here":
        print("[ERROR] Please configure IndexTTS2 speaker_audio_url.", file=sys.stderr)
        sys.exit(1)

    base_url = config_env(
        config,
        "IndexTTS2",
        "base_url",
        ["INDEX_TTS2_BASE_URL", "AI302_BASE_URL"],
        "https://api.302.ai",
    ).rstrip("/")
    emotion_vector = parse_emotion_vector(
        config_env(config, "IndexTTS2", "emotion_vector", ["INDEX_TTS2_EMOTION_VECTOR"], "")
    )
    settings = {
        "provider": "index_tts2",
        "api_key": api_key,
        "base_url": base_url,
        "speaker_audio_url": speaker_audio_url,
        "emotion_audio_url": config_env(
            config,
            "IndexTTS2",
            "emotion_audio_url",
            ["INDEX_TTS2_EMOTION_AUDIO_URL", "AI302_EMOTION_AUDIO_URL"],
            "",
        ),
        "emotion_alpha": parse_optional_float(
            config_env(config, "IndexTTS2", "emotion_alpha", ["INDEX_TTS2_EMOTION_ALPHA"], "")
        ),
        "emotion_vector": emotion_vector,
        "use_emotion_text": parse_bool(
            config_env(config, "IndexTTS2", "use_emotion_text", ["INDEX_TTS2_USE_EMOTION_TEXT"], "false")
        ),
        "emotion_text": config_env(
            config,
            "IndexTTS2",
            "emotion_text",
            ["INDEX_TTS2_EMOTION_TEXT"],
            "",
        ),
        "timeout": config.getint("IndexTTS2", "timeout", fallback=60),
        "poll_interval": config.getfloat("IndexTTS2", "poll_interval", fallback=2.0),
        "max_wait_seconds": config.getint("IndexTTS2", "max_wait_seconds", fallback=900),
    }
    print(f"[INFO] 302.ai IndexTTS2 API key: {mask_secret(api_key)}")
    print(f"[INFO] IndexTTS2 base_url: {base_url}")
    print(f"[INFO] IndexTTS2 speaker_audio_url: {speaker_audio_url}")
    return settings


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


def generate_tts_fish(text, output_path, settings):
    url = f"{settings['base_url']}/tts"
    payload = {
        "text": text,
        "reference_id": settings["reference_id"],
        "format": settings["format"],
        "latency": settings["latency"],
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json; charset=utf-8",
        "model": settings["model"],
    }

    response = requests.post(url, headers=headers, data=body, timeout=settings["timeout"])
    if response.status_code >= 400:
        error_text = response.text[:800] if response.text else response.reason
        raise RuntimeError(f"Fish TTS HTTP {response.status_code}: {error_text}")

    temp_path = f"{output_path}.tmp"
    with open(temp_path, "wb") as handle:
        handle.write(response.content)
    if os.path.getsize(temp_path) < 1024:
        raise RuntimeError("Fish TTS response is too small")
    os.replace(temp_path, output_path)

    duration = get_audio_duration(output_path)
    if duration <= 0:
        raise RuntimeError("Generated Fish audio has zero duration")
    return duration


def submit_index_tts2_task(text, settings):
    if len(text) > 2048:
        raise ValueError("IndexTTS2 text must be 2048 characters or fewer")
    payload = {
        "text": text,
        "speaker_audio_url": settings["speaker_audio_url"],
    }
    if settings["emotion_audio_url"]:
        payload["emotion_audio_url"] = settings["emotion_audio_url"]
    if settings["emotion_alpha"] is not None:
        payload["emotion_alpha"] = settings["emotion_alpha"]
    if settings["emotion_vector"] is not None:
        payload["emotion_vector"] = settings["emotion_vector"]
    if settings["use_emotion_text"]:
        payload["use_emotion_text"] = True
        if settings["emotion_text"]:
            payload["emotion_text"] = settings["emotion_text"]

    url = f"{settings['base_url']}/302/index_tts2/task"
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json; charset=utf-8",
        },
        data=body,
        timeout=settings["timeout"],
    )
    if response.status_code >= 400:
        error_text = response.text[:800] if response.text else response.reason
        raise RuntimeError(f"IndexTTS2 submit HTTP {response.status_code}: {error_text}")
    data = response.json()
    task_id = data.get("task_id") or data.get("taskId")
    if not task_id:
        raise RuntimeError(f"IndexTTS2 submit response did not contain task_id: {data}")
    return task_id


def wait_index_tts2_result(task_id, settings):
    url = f"{settings['base_url']}/302/index_tts2/task"
    deadline = time.monotonic() + settings["max_wait_seconds"]
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        time.sleep(settings["poll_interval"])
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {settings['api_key']}"},
            params={"task_id": task_id},
            timeout=settings["timeout"],
        )
        if response.status_code >= 400:
            error_text = response.text[:800] if response.text else response.reason
            raise RuntimeError(f"IndexTTS2 query HTTP {response.status_code}: {error_text}")
        data = response.json()
        state = str(data.get("state") or data.get("status") or "").upper()
        if state in {"SUCCESS", "SUCCEEDED", "COMPLETED"}:
            audio_url = data.get("audio_url") or data.get("url")
            if not audio_url:
                raise RuntimeError(f"IndexTTS2 task succeeded without audio_url: {data}")
            return audio_url
        if state in {"FAILURE", "FAILED", "ERROR"}:
            raise RuntimeError(f"IndexTTS2 task failed: {data}")
        if attempt % max(1, int(30 / settings["poll_interval"])) == 0:
            print(f"      waiting for IndexTTS2 task {task_id} ({attempt * settings['poll_interval']:.0f}s)")

    raise TimeoutError(f"IndexTTS2 task timed out after {settings['max_wait_seconds']}s: {task_id}")


def generate_tts_index_tts2(text, output_path, settings):
    task_id = submit_index_tts2_task(text, settings)
    print(f"      task id: {task_id}")
    audio_url = wait_index_tts2_result(task_id, settings)
    download_audio(audio_url, output_path)

    duration = get_audio_duration(output_path)
    if duration <= 0:
        raise RuntimeError("Generated IndexTTS2 audio has zero duration")
    return duration


def generate_one_segment(idx, segment_record, audio_path, runtime, retries, cache_hash):
    tts_text = segment_record["tts_text"]
    subtitle_text = segment_record["subtitle_text"]
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
            if runtime["provider"] == "fish":
                duration = generate_tts_fish(tts_text, audio_path, runtime["fish"])
            elif runtime["provider"] == "index_tts2":
                duration = generate_tts_index_tts2(tts_text, audio_path, runtime["index_tts2"])
            else:
                duration = generate_tts_runninghub(
                    tts_text,
                    audio_path,
                    runtime["api_key"],
                    runtime.get("reference_audio"),
                    runtime.get("tone", "\u81ea\u7136"),
                )
            return {
                "index": idx,
                "audio_path": os.path.abspath(audio_path),
                "duration": duration,
                "text_hash": text_hash(tts_text),
                "cache_hash": cache_hash,
                "text": subtitle_text,
                "subtitle_text": subtitle_text,
                "tts_text": tts_text,
                "reused": False,
            }
        except Exception as exc:
            last_error = exc
            print(f"[WARN] Segment {idx} attempt {attempt}/{retries} failed: {exc}", file=sys.stderr)
            time.sleep(min(10, attempt * 2))

    raise RuntimeError(f"Segment {idx} failed after {retries} attempts: {last_error}")


def prepare_segments(sentences, config, output_dir, concurrency, force_tts=False):
    provider = get_tts_provider(config)
    reference_audio = None
    tone = None
    if provider == "fish":
        fish_settings = load_fish_settings(config)
        runtime = {
            "provider": "fish",
            "fish": fish_settings,
        }
    elif provider == "index_tts2":
        index_tts2_settings = load_index_tts2_settings(config)
        runtime = {
            "provider": "index_tts2",
            "index_tts2": index_tts2_settings,
        }
    else:
        api_key = get_api_key(config)
        reference_audio, tone = load_voice_settings(config)
        runtime = {
            "provider": "runninghub",
            "api_key": api_key,
            "reference_audio": reference_audio,
            "tone": tone,
        }
    cache_identity = tts_cache_identity(config, reference_audio, tone)
    retries = config.getint("TTS", "retries", fallback=3)

    temp_dir = os.path.join(output_dir, "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)
    manifest_path = os.path.join(temp_dir, "manifest.json")
    manifest = read_manifest(manifest_path)

    segments = normalize_sentence_records(sentences)
    total = len(segments)
    if not total:
        raise RuntimeError("Sentence list is empty after normalization")

    print(f"\n[TTS] Generating voiceover for {total} segments")
    print(f"      provider: {provider}")
    print(f"      concurrency: {concurrency}")
    print(f"      retries: {retries}")
    if provider == "runninghub" and reference_audio:
        print(f"      reference audio: {reference_audio}")
    if provider == "runninghub":
        print(f"      tone: {tone}")

    results = {}
    pending = []
    segment_extension = ".wav" if provider == "index_tts2" else ".mp3"

    for idx, segment_record in enumerate(segments, start=1):
        subtitle_text = segment_record["subtitle_text"]
        tts_text = segment_record["tts_text"]
        audio_path = os.path.join(temp_dir, f"segment_{idx:03d}{segment_extension}")
        key = str(idx)
        expected_text_hash = text_hash(tts_text)
        expected_cache_hash = segment_cache_hash(tts_text, cache_identity)
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
                "text": subtitle_text,
                "subtitle_text": subtitle_text,
                "tts_text": tts_text,
                "reused": True,
            }
            print(f"  [{idx}/{total}] reuse {os.path.basename(audio_path)} ({duration:.2f}s)")
            continue

        pending.append((idx, segment_record, audio_path, expected_cache_hash))

    if pending:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
            futures = {
                executor.submit(
                    generate_one_segment,
                    idx,
                    segment_record,
                    audio_path,
                    runtime,
                    retries,
                    expected_cache_hash,
                ): (idx, segment_record)
                for idx, segment_record, audio_path, expected_cache_hash in pending
            }

            for future in as_completed(futures):
                idx, segment_record = futures[future]
                result = future.result()
                results[idx] = result
                print(f"  [{idx}/{total}] generated ({result['duration']:.2f}s): {result['text'][:36]}")
                manifest[str(idx)] = {
                    "text_hash": result["text_hash"],
                    "cache_hash": result["cache_hash"],
                    "tts_identity": cache_identity,
                    "text": result["text"],
                    "subtitle_text": result["subtitle_text"],
                    "tts_text": result["tts_text"],
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
            "subtitle_text": result["subtitle_text"],
            "tts_text": result["tts_text"],
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
        text = segment.get("subtitle_text") or segment.get("text", "")
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
    parser.add_argument("--skip-clean", action="store_true", help="Disable TTS text cleanup")
    args = parser.parse_args()

    if os.path.isabs(args.config):
        config_path = args.config
    else:
        project_root = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(project_root, args.config)
    config = load_config(os.path.abspath(config_path))

    pause = args.pause if args.pause is not None else config.getfloat("TextToSRT", "pause", fallback=0.5)
    concurrency = args.concurrency if args.concurrency else config.getint("TTS", "concurrency", fallback=1)
    provider = get_tts_provider(config)
    if provider == "fish":
        provider_limit = config.getint("FishAudio", "concurrency", fallback=5)
    elif provider == "index_tts2":
        provider_limit = config.getint("IndexTTS2", "concurrency", fallback=5)
    else:
        provider_limit = 8
    concurrency = max(1, min(concurrency, provider_limit))

    with open(args.sentences, "r", encoding="utf-8-sig") as handle:
        sentences = json.load(handle)

    os.makedirs(args.output_dir, exist_ok=True)

    try:
        if args.skip_clean:
            sentences_for_tts = normalize_sentence_records(sentences)
        else:
            sentences_for_tts = prepare_tts_sentence_records(
                sentences,
                config,
                args.output_dir,
                skip_clean=False,
            )
        segments = prepare_segments(sentences_for_tts, config, args.output_dir, concurrency, args.force_tts)
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
            "tts_sentences_path": os.path.abspath(os.path.join(args.output_dir, "tts_sentences.json"))
            if os.path.exists(os.path.join(args.output_dir, "tts_sentences.json"))
            else None,
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
