#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Split source text into natural TTS/subtitle segments."""

import argparse
import configparser
import io
import json
import os
import re
import sys
from datetime import timedelta

from anthropic import Anthropic


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


def load_config(config_path):
    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8-sig")
    return config


def split_text_with_ai(text, api_key, min_chars=8, max_chars=24, base_url=None):
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = Anthropic(**client_kwargs)

    prompt = f"""请把下面文案分成适合中文口播和单行字幕的短句。

要求：
1. 每句尽量 {min_chars}-{max_chars} 个中文字符，英文词组可以略微放宽。
2. 不要拆出单字、孤立标点、或语义残片。
3. 保留关键标点，节奏自然，适合逐句配音。
4. 只返回 JSON 字符串数组，不要额外说明。

文案：
{text}
"""

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = message.content[0].text.strip()
    if "```json" in response_text:
        response_text = response_text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```", 1)[1].split("```", 1)[0].strip()

    sentences = json.loads(response_text)
    if not isinstance(sentences, list):
        raise ValueError("AI splitter did not return a JSON array")
    return sentences


def simple_split(text):
    """Fallback splitter that keeps sentence-ending punctuation."""
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    pattern = r"[^。！？!?；;\n]+[。！？!?；;]?"

    sentences = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for match in re.finditer(pattern, paragraph):
            sentence = match.group(0).strip()
            if sentence:
                sentences.append(sentence)
    return sentences


def split_long_sentence(sentence, max_chars, min_chars=8):
    """Split long text into natural single-line subtitle chunks."""
    max_units = max_chars * 2

    def visual_len(value):
        return sum(1 if ord(char) < 128 else 2 for char in value)

    def fits(value):
        return visual_len(value) <= max_units

    sentence = sentence.strip()
    if fits(sentence):
        return [sentence]

    break_pattern = r".+?(?:——|[，、；;：:,.])|.+$"
    pieces = [piece.strip() for piece in re.findall(break_pattern, sentence) if piece.strip()]
    chunks = []
    current = ""

    def hard_split(piece):
        split_chunks = []
        while not fits(piece):
            split_at = len(piece)
            units = 0
            for pos, char in enumerate(piece, start=1):
                units += 1 if ord(char) < 128 else 2
                if units > max_units:
                    split_at = max(1, pos - 1)
                    break

            for pos in range(split_at, min_chars, -1):
                if piece[pos - 1] in "，、；;：:,.。！？!?":
                    split_at = pos
                    break
            else:
                for pos in range(split_at, max(min_chars, split_at - 8), -1):
                    if piece[pos - 1].isspace():
                        split_at = pos
                        break
            if split_at == len(piece):
                split_at = max(1, len(piece) - 1)
            for pos in range(split_at, max(min_chars, split_at - 10), -1):
                if piece[pos - 1] in "）)]}\"'”":
                    split_at = pos
                    break
            if split_at == len(piece):
                for pos in range(split_at, max(min_chars, split_at - 10), -1):
                    if piece[pos - 1] in "）)]}\"'”":
                        split_at = pos
                        break
            split_chunks.append(piece[:split_at].strip())
            piece = piece[split_at:].strip()
        if piece:
            split_chunks.append(piece)
        return split_chunks

    def absorb_leading_punctuation(items):
        output = []
        for item in items:
            item = item.strip()
            while item and item[0] in "，、；;：:,.。！？!?":
                if output and visual_len(output[-1] + item[0]) <= max_units + 2:
                    output[-1] += item[0]
                    item = item[1:].strip()
                else:
                    break
            if item:
                output.append(item)
        return output

    def rebalance_short_tail(items):
        balanced_items = []
        for item in items:
            if balanced_items and len(item) < min_chars and fits(balanced_items[-1] + item):
                balanced_items[-1] += item
            else:
                balanced_items.append(item)
        return balanced_items

    for piece in pieces:
        if not fits(piece):
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(hard_split(piece))
        elif current and fits(current + piece):
            current += piece
        else:
            if current:
                chunks.append(current)
            current = piece

    if current:
        chunks.append(current)

    balanced = rebalance_short_tail(absorb_leading_punctuation(chunks))

    return [chunk for chunk in balanced if chunk]


def normalize_sentences(sentences, max_chars, min_chars=8):
    normalized = []
    for sentence in sentences:
        if isinstance(sentence, dict):
            text = str(sentence.get("text", "")).strip()
        else:
            text = str(sentence).strip()
        if not text:
            continue
        normalized.extend(split_long_sentence(text, max_chars, min_chars))
    return normalized


def calculate_duration(text, speed=4.0):
    return len(text) / speed


def format_timestamp(seconds):
    td = timedelta(seconds=seconds)
    total = td.total_seconds()
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = int(total % 60)
    millis = int((total % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(sentences, speed=4.0, pause=0.5):
    srt_lines = []
    current_time = 0.0
    for idx, sentence in enumerate(sentences, start=1):
        start_time = current_time
        end_time = start_time + calculate_duration(sentence, speed)
        srt_lines.append(str(idx))
        srt_lines.append(f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}")
        srt_lines.append(sentence)
        srt_lines.append("")
        current_time = end_time + pause
    return "\n".join(srt_lines), max(0.0, current_time - pause)


def resolve_config_path(config_arg):
    if os.path.isabs(config_arg):
        return config_arg
    return os.path.join(os.path.dirname(__file__), config_arg)


def main():
    parser = argparse.ArgumentParser(description="Split text into TTS/subtitle segments")
    parser.add_argument("--input", required=True, help="Input text file")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--config", default="../config/config.ini", help="Config file path")
    args = parser.parse_args()

    config_path = resolve_config_path(args.config)
    config = load_config(config_path)

    min_chars = config.getint("TextToSRT", "min_chars", fallback=8)
    max_chars = config.getint("TextToSRT", "max_chars", fallback=24)
    enable_ai_split = config.getboolean("TextToSRT", "enable_ai_split", fallback=True)
    claude_api_key = config.get("Claude", "api_key", fallback="")
    claude_base_url = config.get("Claude", "base_url", fallback="").strip() or None

    if not os.path.exists(args.input):
        print(f"[ERROR] Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8-sig") as handle:
        text = handle.read().strip()
    if not text:
        print("[ERROR] Input text is empty", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Read input text: {len(text)} chars")
    if enable_ai_split and claude_api_key and claude_api_key != "your_claude_api_key_here":
        print("[INFO] AI semantic splitting enabled")
        try:
            sentences = split_text_with_ai(text, claude_api_key, min_chars, max_chars, claude_base_url)
        except Exception as exc:
            print(f"[WARN] AI splitting failed, using local fallback: {exc}", file=sys.stderr)
            sentences = simple_split(text)
    else:
        print("[INFO] AI splitting disabled or not configured; using local fallback")
        sentences = simple_split(text)

    sentences = normalize_sentences(sentences, max_chars, min_chars)
    if not sentences:
        print("[ERROR] No sentences generated", file=sys.stderr)
        sys.exit(1)

    print(f"[SUCCESS] Split complete: {len(sentences)} segments")
    for idx, sentence in enumerate(sentences, start=1):
        print(f"  {idx}. {sentence}")

    if args.output:
        output_path = args.output
    else:
        input_dir = os.path.dirname(os.path.abspath(args.input))
        input_name = os.path.splitext(os.path.basename(args.input))[0]
        output_path = os.path.join(input_dir, f"{input_name}_sentences.json")

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(sentences, handle, ensure_ascii=False, indent=2)

    result = {
        "sentences_path": os.path.abspath(output_path),
        "sentence_count": len(sentences),
    }
    print(f"[OUTPUT] {output_path}")
    print(f"\nRESULT_JSON={json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
