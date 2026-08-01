#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Normalize SRT subtitle text for on-screen display.

The MiniMax narration can deliberately use spoken Chinese numerals such as
"二零二五年" or "一百一十四亿". Subtitles are easier to scan when those
phrases are displayed as "2025年" and "114亿". This script keeps timings and
line breaks intact, and only rewrites conservative number/unit patterns.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "○": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}
CN_NUMBER_CHARS = "".join(CN_DIGITS.keys()) + "".join(CN_UNITS.keys())
CN_SIMPLE_DIGIT_CHARS = "".join(CN_DIGITS.keys())
CN_SMALL_NUMBER_CHARS = "".join(CN_DIGITS.keys()) + "十百千"


def chinese_int(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    if all(ch in CN_DIGITS for ch in text):
        return int("".join(str(CN_DIGITS[ch]) for ch in text))

    total = 0
    section = 0
    number = 0
    seen = False
    for ch in text:
        if ch in CN_DIGITS:
            number = CN_DIGITS[ch]
            seen = True
            continue
        unit = CN_UNITS.get(ch)
        if unit is None:
            return None
        seen = True
        if unit < 10000:
            if number == 0:
                number = 1
            section += number * unit
            number = 0
        else:
            section += number
            total += section * unit
            section = 0
            number = 0
    if not seen:
        return None
    return total + section + number


def chinese_decimal(text: str) -> str | None:
    if "点" not in text:
        return None
    integer_text, decimal_text = text.split("点", 1)
    integer = chinese_int(integer_text)
    if integer is None or not decimal_text or not all(ch in CN_DIGITS for ch in decimal_text):
        return None
    decimals = "".join(str(CN_DIGITS[ch]) for ch in decimal_text)
    return f"{integer}.{decimals}"


def display_integer(value: int, suffix: str = "") -> str:
    if value >= 10000 and value % 10000 == 0 and suffix in {"颗", "枚", "次", "人", "个"}:
        return f"{value // 10000}万"
    return str(value)


def replace_year(match: re.Match[str]) -> str:
    digits = "".join(str(CN_DIGITS[ch]) for ch in match.group(1))
    return f"{digits}年"


def replace_month_day(match: re.Match[str]) -> str:
    month = chinese_int(match.group(1))
    day = chinese_int(match.group(2))
    if month is None or day is None:
        return match.group(0)
    return f"{month}月{day}日"


def replace_month(match: re.Match[str]) -> str:
    month = chinese_int(match.group(1))
    if month is None:
        return match.group(0)
    return f"{month}月"


def replace_day(match: re.Match[str]) -> str:
    day = chinese_int(match.group(1))
    if day is None:
        return match.group(0)
    return f"{day}日"


def replace_percent(match: re.Match[str]) -> str:
    number_text = match.group(1)
    value = chinese_decimal(number_text) if "点" in number_text else None
    if value is None:
        integer = chinese_int(number_text)
        if integer is None:
            return match.group(0)
        value = str(integer)
    return f"{value}%"


def replace_alnum_digits(match: re.Match[str]) -> str:
    prefix = match.group(1)
    number = "".join(str(CN_DIGITS[ch]) for ch in match.group(2))
    return f"{prefix}{number}"


def replace_generation_label(match: re.Match[str]) -> str:
    number = "".join(str(CN_DIGITS[ch]) for ch in match.group(1))
    return f"{number}后"


def replace_special_big_suffix(match: re.Match[str]) -> str:
    integer = chinese_int(match.group(1))
    if integer is None:
        return match.group(0)
    return f"{integer}{match.group(2)}"


def replace_mixed_myriad_suffix(match: re.Match[str]) -> str:
    value = chinese_int(match.group(1))
    if value is None:
        return match.group(0)
    return f"{value}{match.group(2)}"


def replace_chinese_amount_unit(match: re.Match[str]) -> str:
    value = chinese_int(match.group(1))
    if value is None:
        return match.group(0)
    return f"{value}{match.group(2)}{match.group(3)}"


def replace_decimal_with_suffix(match: re.Match[str]) -> str:
    value = chinese_decimal(match.group(1))
    if value is None:
        return match.group(0)
    return f"{value}{match.group(2) or ''}"


DISPLAY_SUFFIXES = (
    "多万美元",
    "美元每公斤",
    "亿美元",
    "万美元",
    "美元",
    "多年的",
    "年以上",
    "年的",
    "太瓦",
    "公斤",
    "公里",
    "小时",
    "升",
    "世纪",
    "颗",
    "枚",
    "次",
    "吨",
    "米",
    "年",
    "亿",
    "万",
)
DISPLAY_SUFFIX_RE = "|".join(re.escape(suffix) for suffix in DISPLAY_SUFFIXES)


def replace_number_with_suffix(match: re.Match[str]) -> str:
    number_text = match.group(1)
    suffix = match.group(2)
    if number_text in {"万", "亿", "万亿"}:
        return match.group(0)
    if number_text == "一" and suffix in {"次", "年", "年的", "多年的", "年以上"}:
        return match.group(0)
    value = chinese_int(number_text)
    if value is None:
        return match.group(0)
    bare_suffix = suffix
    for prefix in ("多",):
        if bare_suffix.startswith(prefix):
            bare_suffix = bare_suffix[len(prefix) :]
    return f"{display_integer(value, bare_suffix)}{suffix}"


def replace_range_left(match: re.Match[str]) -> str:
    value = chinese_int(match.group(1))
    if value is None:
        return match.group(0)
    return f"{value}{match.group(2)}"


def normalize_display_text(text: str) -> str:
    if not text:
        return text

    cn = CN_NUMBER_CHARS
    simple = CN_SIMPLE_DIGIT_CHARS

    # Dates first, so "二零二五年十二月三日" becomes "2025年12月3日".
    text = re.sub(fr"([{simple}]{{4}})年", replace_year, text)
    text = re.sub(fr"([{cn}]{{1,4}})月([{cn}]{{1,4}})日", replace_month_day, text)
    text = re.sub(fr"(?<![A-Za-z0-9])([{cn}]{{1,4}})月", replace_month, text)
    text = re.sub(fr"(?<![A-Za-z0-9])([{cn}]{{1,4}})日", replace_day, text)

    # Mixed model names and products: B一零六七 -> B1067, V三 -> V3, 波音七四七 -> 波音747.
    text = re.sub(fr"([A-Za-z])([{simple}]+)", replace_alnum_digits, text)
    text = re.sub(fr"(波音)([{simple}]+)", replace_alnum_digits, text)

    # Spoken generation labels use digit-by-digit pronunciation, while display text uses 90后/00后.
    # "九十后" is intentionally excluded because 十 is not a simple digit character.
    text = re.sub(fr"([{simple}]{{2}})后", replace_generation_label, text)

    # Percentages and decimals with explicit units.
    text = re.sub(fr"百分之([{cn}点]+)", replace_percent, text)
    text = re.sub(fr"([{cn}]+点[{simple}]+)(万亿美元|万亿|亿美元|万美元|美元|太瓦|公里|吨|%|)", replace_decimal_with_suffix, text)

    # Big financial shorthand where the unit is part of display convention.
    # Keep "一百一十四亿美元" as "114亿美元", not "11400000000美元".
    text = re.sub(fr"([{CN_SMALL_NUMBER_CHARS}]+)(亿|万)(美元)", replace_chinese_amount_unit, text)
    text = re.sub(fr"([{cn}]+)(万亿美元|万亿)", replace_special_big_suffix, text)

    # Mixed ten-thousand expressions must be converted as one number:
    # 一万五千升 -> 15000升, rather than the malformed 1万五千升.
    text = re.sub(fr"([{cn}]+万[{CN_SMALL_NUMBER_CHARS}]+)(升|世纪)", replace_mixed_myriad_suffix, text)

    # Range starts such as "六百五十至七百美元".
    text = re.sub(fr"([{CN_SMALL_NUMBER_CHARS}]+)(至|到)", replace_range_left, text)

    # Conservative number+unit display conversion.
    # Keep natural approximations such as "几千年" and "数百年" in Chinese.
    # A numeric rewrite here would produce awkward hybrids like "几1000年".
    text = re.sub(fr"(?<![几数])([{cn}]+)({DISPLAY_SUFFIX_RE})", replace_number_with_suffix, text)

    # MiniMax may already emit Arabic digits. Restore natural standalone time phrases.
    text = re.sub(r"(?<!\d)1年(?!\d)", "一年", text)

    return text


def normalize_srt_content(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", normalized.strip())
    output_blocks: list[str] = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) >= 3 and "-->" in lines[1]:
            text_lines = [normalize_display_text(line) for line in lines[2:]]
            output_blocks.append("\n".join([lines[0], lines[1], *text_lines]))
        else:
            output_blocks.append(block)
    return "\n\n".join(output_blocks).strip() + "\n"


def normalize_srt_file(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    src = Path(input_path)
    dst = Path(output_path) if output_path else src
    content = src.read_text(encoding="utf-8-sig")
    dst.write_text(normalize_srt_content(content), encoding="utf-8")
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize SRT subtitles for display")
    parser.add_argument("input_srt")
    parser.add_argument("output_srt", nargs="?")
    args = parser.parse_args()

    output = normalize_srt_file(args.input_srt, args.output_srt)
    print(f"[OK] display subtitles: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
