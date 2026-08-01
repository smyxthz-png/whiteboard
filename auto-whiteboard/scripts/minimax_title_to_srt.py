#!/usr/bin/env python3
"""Convert MiniMax .title timestamp JSON to SRT subtitles.

Usage:
    python3 title_to_srt.py <input_title_path> <input_wav_path> [output_srt_path]

The input .title file is expected to be a JSON array where each item contains
sentence-level text plus timestamped_words with character-level timestamps.
"""

import json
import math
import re
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TARGET_CHARS = 20
MAX_CHARS = 26
MIN_CHARS = 6

TARGET_DURATION_MS = 3000
MAX_DURATION_MS = 5500
MIN_DURATION_MS = 700

COMMA_BREAK_MIN_CHARS = 4
DUNHAO_BREAK_MIN_CHARS = 14
PUNCT_BREAK_MAX_CHARS = 32
PUNCT_BREAK_MAX_DURATION_MS = 6500

TAIL_EXTEND_MAX_MS = 300
GAP_BEFORE_NEXT_MS = 80
MIN_SUBTITLE_GAP_MS = 40

ENERGY_WINDOW_MS = 20
ENERGY_HOP_MS = 10
STABLE_SPEECH_MS = 80
START_SEARCH_MS = 1400
START_PREROLL_MS = 60
START_LONG_SILENCE_MS = 250
START_SILENCE_DELAY_MS = 350
END_SEARCH_BEFORE_MS = 1500
END_SEARCH_AFTER_MS = 800
END_POSTROLL_MS = 160

STRONG_BREAKS = set("。！？；：")
COMMA_BREAKS = set("，")
DUNHAO_BREAKS = set("、")
OPEN_BRACKETS = set("（(")
CLOSE_BRACKETS = set("）)")
_QUOTE_OPEN_CHARS = (chr(0x201C), chr(0x2018), '"')   # " ' "
_QUOTE_CLOSE_CHARS = (chr(0x201D), chr(0x2019), '"')   # " ' "
OPEN_QUOTES = set(_QUOTE_OPEN_CHARS)
CLOSE_QUOTES = set(_QUOTE_CLOSE_CHARS)
PAIR_MAP = {
    chr(0xFF09): chr(0xFF08), ")": "(",                  # （） and ()
    chr(0x201D): chr(0x201C), chr(0x2019): chr(0x2018),  # "" and ''
    '"': '"',                                             # ASCII ""
}
_ALL_OPEN = OPEN_BRACKETS | OPEN_QUOTES
_ALL_CLOSE = CLOSE_BRACKETS | CLOSE_QUOTES
TRAILING_SUBTITLE_PUNCT = "，。！？；：、,.!?;:"
SOFT_BREAK_WORDS = {
    "的",
    "了",
    "呢",
    "吧",
    "吗",
    "是",
    "在",
    "但",
    "而",
    "所以",
    "因为",
    "如果",
    "然后",
}
MAX_SOFT_BREAK_LEN = max(len(word) for word in SOFT_BREAK_WORDS)

_ENGLISH_RE = re.compile(r"^[A-Za-z]+$")
_STARTS_WITH_DIGIT_RE = re.compile(r"^[0-9]")
_STARTS_WITH_LETTER_RE = re.compile(r"^[A-Za-z]")
_DECIMAL_SPLIT_SUFFIX_RE = re.compile(r"([,，、]?\s*)0$")
_PERCENT_START_RE = re.compile(r"^\d+(?:\.\d+)?%")


def trailing_break_punct(word: str) -> str | None:
    stripped = word.strip()
    if not stripped:
        return None

    for ch in reversed(stripped):
        if ch in CLOSE_BRACKETS or ch in CLOSE_QUOTES:
            continue
        if ch in STRONG_BREAKS or ch in COMMA_BREAKS or ch in DUNHAO_BREAKS:
            return ch
        break

    return None


def is_duplicate_frame_end(words: list[dict[str, Any]], i: int) -> bool:
    """Check if word i is the last frame of a group of duplicate frames.

    MiniMax TTS splits English words into multiple timestamped_words entries
    that share the same word/word_begin/word_end but have different time_begin/time_end.
    A break should only happen at the last frame of such a group.
    """
    if i + 1 < len(words):
        cur, nxt = words[i], words[i + 1]
        if cur["word_begin"] == nxt["word_begin"] and cur["word_end"] == nxt["word_end"]:
            return False
    return True


def is_english_word_end(words: list[dict[str, Any]], i: int) -> bool:
    if not _ENGLISH_RE.match(word_text(words[i])):
        return False
    if i + 1 >= len(words):
        return True
    nxt = word_text(words[i + 1])
    if _ENGLISH_RE.match(nxt):
        return False
    if _STARTS_WITH_DIGIT_RE.match(nxt):
        return False
    # Mixed token like "s，" starts with letter — english content continues
    if _STARTS_WITH_LETTER_RE.match(nxt):
        return False
    # Skip space and check what follows (e.g. "Antigravity 2.0", "YouTube Shorts")
    if nxt == " " and i + 2 < len(words):
        after_space = word_text(words[i + 2])
        if _STARTS_WITH_DIGIT_RE.match(after_space):
            return False
        if _STARTS_WITH_LETTER_RE.match(after_space):
            return False
    return True


def is_inside_english_word(words: list[dict[str, Any]], i: int) -> bool:
    """Check if position i is inside a multi-frame english word (not at its true end).

    MiniMax may split one english word into consecutive letter-only frames
    (e.g. "Sh" -> "ort" -> "s，"). Position i is "inside" if it is a
    letter-only frame but NOT a true english word end.
    """
    word = word_text(words[i])
    if not _ENGLISH_RE.match(word):
        return False
    return not is_english_word_end(words, i)


def find_bracket_pairs(words: list[dict[str, Any]], start: int, end: int) -> list[tuple[int, int]]:
    """Find matched bracket/quote pairs in [start, end].

    Returns [(open_idx, close_idx), ...] for complete pairs only.
    Unmatched open/close symbols are ignored (no constraint).
    Close index extends to the last duplicate frame (e.g. "ls）" -> "s）").
    """
    raw_pairs: list[tuple[int, int]] = []
    stack: list[tuple[int, str]] = []  # (word_index, open_char)
    for i in range(start, end + 1):
        w = word_text(words[i])
        for ch in w:
            # Try close first (handles ambiguous chars like " that are both open and close)
            if ch in _ALL_CLOSE:
                expected_open = PAIR_MAP.get(ch)
                matched = False
                if stack and expected_open:
                    for si in range(len(stack) - 1, -1, -1):
                        if stack[si][1] == expected_open:
                            raw_pairs.append((stack[si][0], i))
                            stack.pop(si)
                            matched = True
                            break
                if not matched and ch not in _ALL_OPEN:
                    pass  # Unmatched close, ignore
                elif not matched:
                    stack.append((i, ch))
            elif ch in _ALL_OPEN:
                stack.append((i, ch))

    # Extend close_idx to the last duplicate frame
    pairs: list[tuple[int, int]] = []
    for open_idx, close_idx in raw_pairs:
        last = close_idx
        while last + 1 <= end:
            cur_we = int(words[last]["word_end"])
            nxt_we = int(words[last + 1]["word_end"])
            nxt_wb = int(words[last + 1]["word_begin"])
            if nxt_wb < cur_we and nxt_we == cur_we:
                last += 1
            else:
                break
        pairs.append((open_idx, last))
    return pairs


@dataclass
class Chunk:
    segment_index: int
    start_word_index: int
    end_word_index: int
    start_ms: float
    end_ms: float
    text: str

    @property
    def chars(self) -> int:
        return len(self.text.strip())

    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms


class TitleFormatError(ValueError):
    pass


class AudioFormatError(ValueError):
    pass


@dataclass
class AudioEnergy:
    frames: list[tuple[float, float]]
    threshold_db: float
    duration_ms: float

    def is_speech_db(self, db: float) -> bool:
        return db >= self.threshold_db

    def find_stable_speech_start(self, start_ms: float, end_ms: float) -> float | None:
        needed = max(1, int(math.ceil(STABLE_SPEECH_MS / ENERGY_HOP_MS)))
        run = 0
        run_start: float | None = None
        for frame_start, db in self.frames:
            if frame_start < start_ms:
                continue
            if frame_start > end_ms:
                break
            if self.is_speech_db(db):
                if run == 0:
                    run_start = frame_start
                run += 1
                if run >= needed and run_start is not None:
                    return run_start
            else:
                run = 0
                run_start = None
        return None

    def find_last_stable_speech_end(self, start_ms: float, end_ms: float) -> float | None:
        needed = max(1, int(math.ceil(STABLE_SPEECH_MS / ENERGY_HOP_MS)))
        run = 0
        last_end: float | None = None
        for frame_start, db in self.frames:
            if frame_start < start_ms:
                continue
            if frame_start > end_ms:
                break
            if self.is_speech_db(db):
                run += 1
                if run >= needed:
                    last_end = frame_start + ENERGY_WINDOW_MS
            else:
                run = 0
        return last_end

    def find_speech_after_start_silence(self, start_ms: float, end_ms: float) -> float | None:
        silence_start: float | None = None
        silence_end: float | None = None
        silence_deadline = start_ms + START_SILENCE_DELAY_MS

        for frame_start, db in self.frames:
            if frame_start < start_ms:
                continue
            if frame_start > end_ms:
                break

            if not self.is_speech_db(db):
                if silence_start is None:
                    if frame_start > silence_deadline:
                        break
                    silence_start = frame_start
                silence_end = frame_start + ENERGY_WINDOW_MS
                if silence_end - silence_start >= START_LONG_SILENCE_MS:
                    return self.find_stable_speech_start(silence_end, end_ms)
            else:
                silence_start = None
                silence_end = None

        return None


def error(message: str) -> None:
    print(json.dumps({"status": "error", "error": message}, ensure_ascii=False))


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def load_title(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise TitleFormatError(f"input file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TitleFormatError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise TitleFormatError("title JSON must be a top-level array")

    for i, segment in enumerate(data):
        prefix = f"segment[{i}]"
        if not isinstance(segment, dict):
            raise TitleFormatError(f"{prefix} must be an object")
        if not isinstance(segment.get("text"), str):
            raise TitleFormatError(f"{prefix}.text must be a string")
        if "text_begin" not in segment or "text_end" not in segment:
            raise TitleFormatError(f"{prefix} must contain text_begin and text_end")
        if not isinstance(segment.get("timestamped_words"), list):
            raise TitleFormatError(f"{prefix}.timestamped_words must be an array")

        for j, word in enumerate(segment["timestamped_words"]):
            validate_word(word, f"{prefix}.timestamped_words[{j}]")

    return data


def validate_word(word: Any, prefix: str) -> None:
    if not isinstance(word, dict):
        raise TitleFormatError(f"{prefix} must be an object")

    required = ["word", "word_begin", "word_end", "time_begin", "time_end"]
    for key in required:
        if key not in word:
            raise TitleFormatError(f"{prefix} missing {key}")

    if not isinstance(word["word"], str):
        raise TitleFormatError(f"{prefix}.word must be a string")

    for key in ["word_begin", "word_end"]:
        if not isinstance(word[key], int):
            raise TitleFormatError(f"{prefix}.{key} must be an integer")

    for key in ["time_begin", "time_end"]:
        if not isinstance(word[key], (int, float)):
            raise TitleFormatError(f"{prefix}.{key} must be a number")

    if word["word_end"] < word["word_begin"]:
        raise TitleFormatError(f"{prefix}.word_end is before word_begin")
    if word["time_end"] < word["time_begin"]:
        raise TitleFormatError(f"{prefix}.time_end is before time_begin")


def default_output_path(input_path: Path) -> Path:
    if input_path.suffix:
        return input_path.with_suffix(".srt")
    return input_path.with_name(f"{input_path.name}.srt")


def load_audio_energy(path: Path) -> AudioEnergy:
    if not path.exists():
        raise AudioFormatError(f"audio file not found: {path}")

    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frame_count = wav.getnframes()
            raw = wav.readframes(frame_count)
    except wave.Error as exc:
        raise AudioFormatError(f"invalid WAV file: {exc}") from exc

    if channels <= 0:
        raise AudioFormatError("WAV must have at least one channel")
    if sample_rate <= 0:
        raise AudioFormatError("WAV sample rate must be positive")
    if sample_width not in (1, 2, 3, 4):
        raise AudioFormatError(f"unsupported WAV sample width: {sample_width}")

    samples = decode_wav_samples(raw, sample_width, channels)
    if not samples:
        raise AudioFormatError("WAV contains no samples")

    duration_ms = len(samples) / sample_rate * 1000
    frames = build_energy_frames(samples, sample_rate)
    threshold_db = estimate_threshold_db([db for _, db in frames])
    return AudioEnergy(frames=frames, threshold_db=threshold_db, duration_ms=duration_ms)


def decode_wav_samples(raw: bytes, sample_width: int, channels: int) -> list[float]:
    frame_size = sample_width * channels
    frame_count = len(raw) // frame_size
    samples: list[float] = []

    for frame_index in range(frame_count):
        offset = frame_index * frame_size
        total = 0.0
        for channel in range(channels):
            start = offset + channel * sample_width
            total += decode_pcm_sample(raw[start : start + sample_width], sample_width)
        samples.append(total / channels)

    return samples


def decode_pcm_sample(data: bytes, sample_width: int) -> float:
    if sample_width == 1:
        return (data[0] - 128) / 128.0
    if sample_width == 2:
        return int.from_bytes(data, "little", signed=True) / 32768.0
    if sample_width == 3:
        sign_extended = data + (b"\xff" if data[2] & 0x80 else b"\x00")
        return int.from_bytes(sign_extended, "little", signed=True) / 8388608.0
    return int.from_bytes(data, "little", signed=True) / 2147483648.0


def build_energy_frames(samples: list[float], sample_rate: int) -> list[tuple[float, float]]:
    window = max(1, int(sample_rate * ENERGY_WINDOW_MS / 1000))
    hop = max(1, int(sample_rate * ENERGY_HOP_MS / 1000))
    frames: list[tuple[float, float]] = []

    for start in range(0, len(samples), hop):
        end = min(len(samples), start + window)
        if end <= start:
            break
        rms = math.sqrt(sum(sample * sample for sample in samples[start:end]) / (end - start))
        db = 20 * math.log10(max(rms, 1e-9))
        frames.append((start / sample_rate * 1000, db))
        if end == len(samples):
            break

    return frames


def estimate_threshold_db(values: list[float]) -> float:
    if not values:
        return -45.0

    sorted_values = sorted(values)
    low = percentile(sorted_values, 0.10)
    high = percentile(sorted_values, 0.90)
    if high - low < 12:
        estimated = high - 12
    else:
        estimated = low + (high - low) * 0.35
    return max(-55.0, min(-30.0, estimated))


def percentile(sorted_values: list[float], ratio: float) -> float:
    if not sorted_values:
        return -90.0
    index = min(len(sorted_values) - 1, max(0, int(round((len(sorted_values) - 1) * ratio))))
    return sorted_values[index]


def format_srt_time(ms: float) -> str:
    rounded = max(0, int(round(ms)))
    hours = rounded // 3_600_000
    rounded %= 3_600_000
    minutes = rounded // 60_000
    rounded %= 60_000
    seconds = rounded // 1_000
    millis = rounded % 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def word_text(word: dict[str, Any]) -> str:
    return str(word.get("word", ""))


def chunk_text(segment: dict[str, Any], words: list[dict[str, Any]], start: int, end: int) -> str:
    text = segment["text"]
    text_begin = int(segment["text_begin"])
    first = words[start]
    last = words[end]

    local_start = int(first["word_begin"]) - text_begin
    local_end = int(last["word_end"]) - text_begin
    if 0 <= local_start <= local_end <= len(text):
        sliced = text[local_start:local_end].strip()
        if sliced:
            return clean_subtitle_text(sliced)

    return clean_subtitle_text("".join(word_text(word) for word in words[start : end + 1]))


def chunk_text_from_words(words: list[dict[str, Any]], start: int, end: int) -> str:
    """Build subtitle text while collapsing MiniMax pronunciation frames.

    MiniMax often repeats one original token for each spoken character of a
    normalized number, e.g. "384万" appears six times for 三/百/八/十/四/万.
    The timing frames are useful, but subtitle text should show the source
    token once.
    """
    parts = []
    last_span = None
    for word in words[start : end + 1]:
        span = (int(word["word_begin"]), int(word["word_end"]))
        if span == last_span:
            continue
        parts.append(word_text(word))
        last_span = span
    return clean_subtitle_text("".join(parts))


def clean_subtitle_text(text: str) -> str:
    stripped = text.strip()
    stripped = fix_decimal_spacing(stripped)
    cleaned = stripped.rstrip(TRAILING_SUBTITLE_PUNCT).strip()
    return cleaned or stripped


def fix_decimal_spacing(text: str) -> str:
    text = re.sub(r"(?<=\d)\.\s+(?=\d)", ".", text)
    text = re.sub(r"(?<=\d),\s+(?=\d)", ".", text)
    return text


def find_token_time(segment: dict[str, Any], chunk: Chunk, token: str) -> tuple[float, float] | None:
    words = segment["timestamped_words"]
    for i in range(chunk.end_word_index, chunk.start_word_index - 1, -1):
        if word_text(words[i]).strip() == token:
            return float(words[i]["time_begin"]), float(words[i]["time_end"])
    return None


def repair_cross_chunk_decimals(chunks: list[Chunk], data: list[dict[str, Any]]) -> None:
    for i in range(len(chunks) - 1):
        current = chunks[i]
        nxt = chunks[i + 1]
        if not _DECIMAL_SPLIT_SUFFIX_RE.search(current.text):
            continue
        if not _PERCENT_START_RE.match(nxt.text.strip()):
            continue

        repaired_current = _DECIMAL_SPLIT_SUFFIX_RE.sub("", current.text).rstrip(" ,，、")
        if not repaired_current:
            continue

        current.text = repaired_current
        nxt.text = f"0.{nxt.text.strip()}"

        token_time = find_token_time(data[current.segment_index], current, "0")
        if token_time is None:
            continue
        zero_start, _ = token_time
        new_current_end = min(current.end_ms, max(current.start_ms + MIN_DURATION_MS, zero_start - MIN_SUBTITLE_GAP_MS))
        current.end_ms = new_current_end
        nxt.start_ms = max(current.end_ms + MIN_SUBTITLE_GAP_MS, min(nxt.start_ms, zero_start))


def span_duration(words: list[dict[str, Any]], start: int, end: int) -> float:
    return float(words[end]["time_end"]) - float(words[start]["time_begin"])


def ends_with_soft_break(words: list[dict[str, Any]], start: int, end: int) -> bool:
    for size in range(1, MAX_SOFT_BREAK_LEN + 1):
        phrase_start = end - size + 1
        if phrase_start < start:
            break
        phrase = "".join(word_text(word) for word in words[phrase_start : end + 1])
        if phrase in SOFT_BREAK_WORDS:
            return True
    return False


def is_break_allowed(words: list[dict[str, Any]], start: int, end: int, chars: int, duration_ms: float) -> bool:
    if not is_duplicate_frame_end(words, end):
        return False
    punct = trailing_break_punct(word_text(words[end]))
    if punct in STRONG_BREAKS:
        return True
    if punct in COMMA_BREAKS:
        return chars >= COMMA_BREAK_MIN_CHARS or duration_ms >= TARGET_DURATION_MS
    if punct in DUNHAO_BREAKS:
        return chars >= DUNHAO_BREAK_MIN_CHARS or duration_ms >= TARGET_DURATION_MS
    if ends_with_soft_break(words, start, end):
        return chars >= TARGET_CHARS or duration_ms >= TARGET_DURATION_MS
    if is_english_word_end(words, end):
        return chars >= TARGET_CHARS or duration_ms >= TARGET_DURATION_MS
    return False


def is_preferred_punctuation_break(word: str, chars: int, duration_ms: float) -> bool:
    punct = trailing_break_punct(word)
    if punct in STRONG_BREAKS:
        return True
    if punct in COMMA_BREAKS:
        return chars >= COMMA_BREAK_MIN_CHARS or duration_ms >= MIN_DURATION_MS
    if punct in DUNHAO_BREAKS:
        return chars >= DUNHAO_BREAK_MIN_CHARS or duration_ms >= TARGET_DURATION_MS
    return False


def break_score(
    words: list[dict[str, Any]],
    start: int,
    end: int,
    target_end: int,
) -> tuple[int, int, int]:
    punct = trailing_break_punct(word_text(words[end]))
    chars = end - start + 1
    duration = span_duration(words, start, end)
    distance = abs(end - target_end)

    if punct in STRONG_BREAKS:
        priority = 0
    elif punct in COMMA_BREAKS:
        priority = 1
    elif punct in DUNHAO_BREAKS:
        priority = 2
    elif ends_with_soft_break(words, start, end):
        priority = 3
    elif is_english_word_end(words, end):
        priority = 3
    else:
        priority = 4

    short_penalty = 1 if chars < MIN_CHARS and duration < MIN_DURATION_MS else 0
    return (priority, short_penalty, distance)


def choose_break(words: list[dict[str, Any]], start: int) -> int:
    total = len(words)
    punct_max_end = min(total - 1, start + PUNCT_BREAK_MAX_CHARS - 1)
    target_end = min(total - 1, start + TARGET_CHARS - 1)

    max_end = min(total - 1, start + MAX_CHARS - 1)
    forced_end = max_end
    for i in range(start, max_end + 1):
        if span_duration(words, start, i) >= MAX_DURATION_MS:
            forced_end = i
            break

    bracket_pairs = find_bracket_pairs(words, start, total - 1)

    def in_brackets(pos: int) -> bool:
        return any(o < pos < c for o, c in bracket_pairs)

    for i in range(start, punct_max_end + 1):
        chars = i - start + 1
        duration = span_duration(words, start, i)
        if not is_duplicate_frame_end(words, i):
            if chars >= MAX_CHARS or duration >= MAX_DURATION_MS:
                break
            continue
        if is_preferred_punctuation_break(word_text(words[i]), chars, duration) and not in_brackets(i):
            return i
        if chars >= MAX_CHARS or duration >= MAX_DURATION_MS:
            break

    search_end = forced_end
    candidates: list[int] = []
    for i in range(start, search_end + 1):
        chars = i - start + 1
        duration = span_duration(words, start, i)
        if is_break_allowed(words, start, i, chars, duration) and not in_brackets(i):
            candidates.append(i)

    # If all candidates are inside brackets, break at the closing bracket
    if not candidates and bracket_pairs:
        for _, close_idx in sorted(bracket_pairs, key=lambda p: p[1]):
            if close_idx > start and is_duplicate_frame_end(words, close_idx):
                candidates.append(close_idx)
                break

    # Safety valve: if still no candidates, retry without bracket constraint
    if not candidates:
        for i in range(start, search_end + 1):
            chars = i - start + 1
            duration = span_duration(words, start, i)
            if is_break_allowed(words, start, i, chars, duration):
                candidates.append(i)

    if candidates:
        mature_candidates = [
            i
            for i in candidates
            if (i - start + 1) >= MIN_CHARS or span_duration(words, start, i) >= MIN_DURATION_MS
        ]
        pool = mature_candidates or candidates
        best = min(pool, key=lambda i: break_score(words, start, i, target_end))
        # Avoid breaking inside an english word — fall back to earlier candidate
        if not is_inside_english_word(words, best):
            return best
        safe = [i for i in pool if not is_inside_english_word(words, i)]
        if safe:
            return min(safe, key=lambda i: break_score(words, start, i, target_end))

    if forced_end < total - 1:
        soft_candidates = [
            i
            for i in range(start, forced_end + 1)
            if is_duplicate_frame_end(words, i)
            and (ends_with_soft_break(words, start, i) or is_english_word_end(words, i))
            and (i - start + 1) >= MIN_CHARS
            and not in_brackets(i)
        ]
        if soft_candidates:
            return min(soft_candidates, key=lambda i: abs(i - target_end))

    # Ensure fallback doesn't land on a duplicate frame's middle position,
    # inside an english word, or inside matched brackets
    fallback = min(target_end, forced_end)
    while fallback < total - 1 and (
        not is_duplicate_frame_end(words, fallback)
        or is_inside_english_word(words, fallback)
        or in_brackets(fallback)
    ):
        fallback += 1
    return fallback


def merge_short_chunks(segment: dict[str, Any], words: list[dict[str, Any]], chunks: list[Chunk]) -> list[Chunk]:
    if len(chunks) <= 1:
        return chunks

    merged: list[Chunk] = []
    i = 0
    while i < len(chunks):
        current = chunks[i]
        if (
            current.chars < MIN_CHARS
            and current.duration_ms < MIN_DURATION_MS
            and i + 1 < len(chunks)
            and current.segment_index == chunks[i + 1].segment_index
            and current.chars + chunks[i + 1].chars <= MAX_CHARS
        ):
            nxt = chunks[i + 1]
            merged.append(
                Chunk(
                    segment_index=current.segment_index,
                    start_word_index=current.start_word_index,
                    end_word_index=nxt.end_word_index,
                    start_ms=current.start_ms,
                    end_ms=nxt.end_ms,
                text=chunk_text_from_words(words, current.start_word_index, nxt.end_word_index),
                )
            )
            i += 2
        elif (
            current.chars < MIN_CHARS
            and current.duration_ms < MIN_DURATION_MS
            and merged
            and current.segment_index == merged[-1].segment_index
            and merged[-1].chars + current.chars <= MAX_CHARS
        ):
            prev = merged[-1]
            merged[-1] = Chunk(
                segment_index=prev.segment_index,
                start_word_index=prev.start_word_index,
                end_word_index=current.end_word_index,
                start_ms=prev.start_ms,
                end_ms=current.end_ms,
                text=chunk_text_from_words(words, prev.start_word_index, current.end_word_index),
            )
            i += 1
        else:
            merged.append(current)
            i += 1

    return merged


def split_segment(segment: dict[str, Any], segment_index: int) -> list[Chunk]:
    words = segment["timestamped_words"]
    if not words:
        warn(f"segment[{segment_index}] has empty timestamped_words, skipped")
        return []

    chunks: list[Chunk] = []
    start = 0
    while start < len(words):
        end = choose_break(words, start)
        chunks.append(
            Chunk(
                segment_index=segment_index,
                start_word_index=start,
                end_word_index=end,
                start_ms=float(words[start]["time_begin"]),
                end_ms=float(words[end]["time_end"]),
                text=chunk_text_from_words(words, start, end),
            )
        )
        start = end + 1

    return merge_short_chunks(segment, words, chunks)


def build_chunks(data: list[dict[str, Any]], audio: AudioEnergy) -> list[Chunk]:
    chunks: list[Chunk] = []
    segment_end_by_index = {
        i: float(segment.get("time_end", segment["timestamped_words"][-1]["time_end"]))
        for i, segment in enumerate(data)
        if segment.get("timestamped_words")
    }

    for segment_index, segment in enumerate(data):
        chunks.extend(split_segment(segment, segment_index))

    repair_cross_chunk_decimals(chunks, data)
    correct_chunk_starts(chunks, audio)
    adjust_chunk_timing(chunks, segment_end_by_index)
    correct_chunk_ends(chunks, audio)
    return chunks


def correct_chunk_starts(chunks: list[Chunk], audio: AudioEnergy) -> None:
    for chunk in chunks:
        search_end = min(chunk.end_ms, chunk.start_ms + START_SEARCH_MS, audio.duration_ms)
        speech_start = audio.find_speech_after_start_silence(chunk.start_ms, search_end)
        if speech_start is None:
            continue

        corrected = max(chunk.start_ms, speech_start - START_PREROLL_MS)
        if corrected < chunk.end_ms - MIN_DURATION_MS:
            chunk.start_ms = corrected


def correct_chunk_ends(chunks: list[Chunk], audio: AudioEnergy) -> None:
    for i, chunk in enumerate(chunks):
        next_chunk = chunks[i + 1] if i + 1 < len(chunks) else None
        next_start = next_chunk.start_ms if next_chunk else audio.duration_ms
        if next_start - chunk.end_ms < 180 and next_chunk is not None:
            continue

        search_start = max(chunk.start_ms, chunk.end_ms - END_SEARCH_BEFORE_MS)
        search_end = min(chunk.end_ms + END_SEARCH_AFTER_MS, next_start, audio.duration_ms)
        speech_end = audio.find_last_stable_speech_end(search_start, search_end)
        if speech_end is None:
            continue

        corrected = min(speech_end + END_POSTROLL_MS, next_start)
        if corrected > chunk.start_ms + MIN_DURATION_MS:
            chunk.end_ms = corrected


def adjust_chunk_timing(chunks: list[Chunk], segment_end_by_index: dict[int, float]) -> None:
    for i, chunk in enumerate(chunks):
        next_chunk = chunks[i + 1] if i + 1 < len(chunks) else None
        segment_end = segment_end_by_index.get(chunk.segment_index)
        max_end = chunk.end_ms

        if next_chunk is not None:
            max_before_next = next_chunk.start_ms - GAP_BEFORE_NEXT_MS
            if max_before_next > chunk.end_ms:
                max_end = min(chunk.end_ms + TAIL_EXTEND_MAX_MS, max_before_next)
        elif segment_end is not None and segment_end > chunk.end_ms:
            max_end = min(chunk.end_ms + TAIL_EXTEND_MAX_MS, segment_end)

        if segment_end is not None:
            max_end = min(max_end, segment_end)

        if max_end > chunk.start_ms:
            chunk.end_ms = max_end


def write_srt(chunks: list[Chunk], output_path: Path) -> None:
    lines: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        lines.extend(
            [
                str(index),
                f"{format_srt_time(chunk.start_ms)} --> {format_srt_time(chunk.end_ms)}",
                chunk.text,
                "",
            ]
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if len(sys.argv) not in (3, 4):
        print(f"Usage: {sys.argv[0]} <input_title_path> <input_wav_path> [output_srt_path]", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    audio_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3]) if len(sys.argv) == 4 else default_output_path(input_path)

    try:
        data = load_title(input_path)
        audio = load_audio_energy(audio_path)
        chunks = build_chunks(data, audio)
        write_srt(chunks, output_path)
    except (TitleFormatError, AudioFormatError) as exc:
        error(str(exc))
        sys.exit(1)
    except OSError as exc:
        error(str(exc))
        sys.exit(1)

    print(
        json.dumps(
            {
                "status": "ok",
                "input": str(input_path),
                "audio": str(audio_path),
                "output": str(output_path),
                "subtitle_count": len(chunks),
                "audio_threshold_db": round(audio.threshold_db, 2),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
