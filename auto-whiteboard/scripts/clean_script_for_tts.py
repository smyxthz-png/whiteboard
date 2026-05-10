#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare TTS-friendly text while preserving the original subtitle text."""

import argparse
import configparser
import io
import json
import os
import re
import sys
import unicodedata

try:
    from anthropic import Anthropic
except Exception:  # pragma: no cover - local regex fallback still works
    Anthropic = None


def configure_stdio():
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


INVALID_API_KEYS = {
    "",
    "your_claude_api_key_here",
    "your_claude_key_here",
}


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


def config_bool(config, section, option, fallback=False):
    raw = config.get(section, option, fallback=None)
    if raw is None:
        return fallback
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def clean_text_with_regex(text):
    """Local deterministic cleanup used before/after LLM cleanup and as fallback."""
    text = str(text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)

    # Markdown and rich-text syntax. Keep the readable content, drop the markup.
    text = re.sub(r"```(?:\w+)?", "", text)
    text = text.replace("```", "")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}[-*+]\s+(?=\S)", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", text)

    # Decorative wrappers are useful on screen, but many TTS engines read them awkwardly.
    quote_trans = str.maketrans({
        "《": "",
        "》": "",
        "「": "",
        "」": "",
        "『": "",
        "』": "",
        "“": "",
        "”": "",
        "‘": "",
        "’": "",
        '"': "",
    })
    text = text.translate(quote_trans)

    # Preserve content and natural pauses while removing symbols that often trip TTS APIs.
    text = re.sub(r"\s*[—–-]{2,}\s*", "，", text)
    text = re.sub(r"[#*_~^|\\<>\[\]{}]", " ", text)
    text = re.sub(r"[\U0001f300-\U0001faff\u2600-\u27bf]", "", text)
    text = re.sub(r"[.。]{3,}", "……", text)
    text = re.sub(r"([,，、；;：:])\1+", r"\1", text)
    text = re.sub(r"([。！？!?])\1+", r"\1", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = text.strip(" \t\n,，、；;：:")

    return text.strip()


def clean_text_for_subtitle(text):
    """Display cleanup: remove markup without changing the spoken content."""
    text = str(text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)

    text = re.sub(r"```(?:\w+)?", "", text)
    text = text.replace("```", "")
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}[-*+]\s+(?=\S)", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", text)
    text = re.sub(r"[#*_~^|\\<>\[\]{}]", " ", text)
    text = re.sub(r"[\U0001f300-\U0001faff\u2600-\u27bf]", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = text.strip(" \t\n")
    if not re.search(r"[\w\u4e00-\u9fff]", text, flags=re.UNICODE):
        return ""

    return text.strip()


def needs_llm_cleanup(original_text, regex_text):
    if original_text != regex_text:
        return True
    return bool(
        re.search(
            r"(```|[#*_~^|\\<>\[\]{}]|[\u200b-\u200f\ufeff]|[\U0001f300-\U0001faff]|[《》「」『』“”]|[—–-]{2,})",
            original_text,
        )
    )


def response_text(message):
    chunks = []
    for block in getattr(message, "content", []) or []:
        if hasattr(block, "text"):
            chunks.append(block.text)
        elif isinstance(block, dict) and block.get("text"):
            chunks.append(block["text"])
    return "\n".join(chunks).strip()


def parse_llm_json_array(raw_text):
    text = raw_text.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])

    if isinstance(data, dict):
        for key in ("texts", "items", "result", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if not isinstance(data, list):
        raise ValueError("LLM cleanup did not return a JSON array")

    values = []
    for item in data:
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, dict):
            values.append(str(item.get("tts_text") or item.get("text") or item.get("cleaned_text") or ""))
        else:
            values.append(str(item))
    return values


def clean_batch_with_llm(texts, api_key, base_url=None, model="claude-3-5-sonnet-20241022"):
    if Anthropic is None:
        raise RuntimeError("anthropic package is not available")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = Anthropic(**client_kwargs)

    payload = [{"index": index + 1, "text": text} for index, text in enumerate(texts)]
    prompt = f"""你是一个中文 TTS 文稿清洗器。请把输入数组中的每条 text 清洗成适合语音合成接口朗读的文本。

严格要求：
1. 只移除或替换会干扰 TTS 的符号、Markdown 标记、装饰性分隔线、零宽字符、表情符号、成对书名号/引号外壳。
2. 保留原文事实、词序、语气、专有名词、数字、英文缩写、诗名、人名和关键标点，不要总结，不要改写，不要扩写。
3. 如果破折号、括号、引号会影响朗读，可以替换成自然停顿标点，但不要删除里面的内容。
4. 输出必须是 JSON 字符串数组，长度和输入完全一致，不要输出解释。

输入：
{json.dumps(payload, ensure_ascii=False)}
"""

    max_tokens = max(1024, min(8192, sum(len(text) for text in texts) * 2 + 1024))
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    cleaned = parse_llm_json_array(response_text(message))
    if len(cleaned) != len(texts):
        raise ValueError(f"LLM cleanup returned {len(cleaned)} items for {len(texts)} inputs")
    return [clean_text_with_regex(item) for item in cleaned]


def original_text_from_sentence(sentence):
    if isinstance(sentence, dict):
        return str(
            sentence.get("original_text")
            or sentence.get("subtitle_text")
            or sentence.get("text")
            or ""
        ).strip()
    return str(sentence or "").strip()


def existing_tts_text_from_sentence(sentence):
    if not isinstance(sentence, dict):
        return ""
    for key in ("tts_text", "cleaned_text"):
        value = str(sentence.get(key) or "").strip()
        if value:
            return value
    return ""


def build_record(sentence, tts_text):
    original_text = original_text_from_sentence(sentence)
    record = sentence.copy() if isinstance(sentence, dict) else {}
    subtitle_text = clean_text_for_subtitle(original_text)
    tts_text = clean_text_with_regex(tts_text) or clean_text_with_regex(subtitle_text)
    if not tts_text:
        return None
    record["text"] = original_text
    record["original_text"] = original_text
    record["subtitle_text"] = subtitle_text or original_text
    record["tts_text"] = tts_text
    record["tts_cleanup_changed"] = tts_text != original_text
    return record


def llm_settings(config):
    api_key = (
        os.environ.get("CLAUDE_API_KEY")
        or config.get("Claude", "api_key", fallback="")
    ).strip()
    base_url = (
        os.environ.get("CLAUDE_BASE_URL")
        or config.get("Claude", "base_url", fallback="")
    ).strip() or None
    model = (
        os.environ.get("TTS_CLEAN_MODEL")
        or config.get("TTS", "clean_for_tts_model", fallback="")
        or config.get("Claude", "model", fallback="")
        or "claude-3-5-sonnet-20241022"
    ).strip()
    return api_key, base_url, model


def clean_sentences(sentences, config):
    """Return records with original subtitle text and cleaned TTS text."""
    if not isinstance(sentences, list):
        raise ValueError("Sentence input must be a JSON array")

    use_llm = config_bool(config, "TTS", "clean_for_tts_with_llm", fallback=True)
    llm_mode = config.get("TTS", "clean_for_tts_llm_mode", fallback="changed").strip().lower()
    batch_size = max(1, config.getint("TTS", "clean_for_tts_batch_size", fallback=20))
    api_key, base_url, model = llm_settings(config)
    has_llm_key = bool(api_key and api_key not in INVALID_API_KEYS)
    use_llm = use_llm and has_llm_key

    records = []
    pending = []
    for sentence in sentences:
        original_text = original_text_from_sentence(sentence)
        if not original_text:
            continue

        existing_tts_text = existing_tts_text_from_sentence(sentence)
        if existing_tts_text:
            record = build_record(sentence, existing_tts_text)
            if record:
                records.append(record)
            continue

        regex_text = clean_text_with_regex(original_text)
        record = build_record(sentence, regex_text)
        if not record:
            continue
        record_index = len(records)
        records.append(record)

        if not use_llm:
            continue
        if llm_mode in {"all", "true", "yes", "1"} or (
            llm_mode in {"changed", "auto"} and needs_llm_cleanup(original_text, regex_text)
        ):
            pending.append((record_index, sentence, original_text))

    print(f"[CLEAN] TTS cleanup prepared {len(records)} records", file=sys.stderr)
    if not use_llm:
        reason = "no valid Claude key" if not has_llm_key else "disabled"
        print(f"[CLEAN] LLM cleanup skipped ({reason}); using local sanitizer", file=sys.stderr)
        return records
    if not pending:
        print("[CLEAN] No suspicious text needed LLM cleanup", file=sys.stderr)
        return records

    print(
        f"[CLEAN] LLM cleanup enabled: {len(pending)} records, batch_size={batch_size}, model={model}",
        file=sys.stderr,
    )
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        batch_indexes = [item[0] for item in batch]
        batch_sentences = [item[1] for item in batch]
        batch_texts = [item[2] for item in batch]
        try:
            cleaned_texts = clean_batch_with_llm(batch_texts, api_key, base_url, model)
        except Exception as exc:
            print(f"[WARN] LLM cleanup batch failed; keeping regex cleanup: {exc}", file=sys.stderr)
            continue

        for record_index, source_sentence, cleaned_text in zip(batch_indexes, batch_sentences, cleaned_texts):
            record = build_record(source_sentence, cleaned_text)
            if record:
                records[record_index] = record

    changed_count = sum(1 for record in records if record.get("tts_cleanup_changed"))
    print(f"[CLEAN] TTS cleanup changed {changed_count}/{len(records)} records", file=sys.stderr)
    return records


def resolve_config_path(config_arg):
    if os.path.isabs(config_arg):
        return os.path.abspath(config_arg)
    project_root = os.path.dirname(os.path.dirname(__file__))
    return os.path.abspath(os.path.join(project_root, config_arg))


def main():
    configure_stdio()

    parser = argparse.ArgumentParser(description="Clean sentence JSON for TTS while preserving subtitle text")
    parser.add_argument("--input", required=True, help="Input JSON file, usually a sentence list")
    parser.add_argument("--output", required=True, help="Output JSON file with text + tts_text")
    parser.add_argument("--config", default="config/config.ini", help="Config file path")
    args = parser.parse_args()

    config = load_config(resolve_config_path(args.config))

    print(f"[INFO] Reading sentences: {args.input}", file=sys.stderr)
    with open(args.input, "r", encoding="utf-8-sig") as handle:
        sentences = json.load(handle)

    cleaned_sentences = clean_sentences(sentences, config)

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(cleaned_sentences, handle, ensure_ascii=False, indent=2)

    result = {
        "cleaned_count": len(cleaned_sentences),
        "changed_count": sum(1 for item in cleaned_sentences if item.get("tts_cleanup_changed")),
        "output_path": os.path.abspath(args.output),
    }
    print(f"[SUCCESS] TTS cleanup complete: {args.output}", file=sys.stderr)
    print(f"RESULT_JSON={json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
