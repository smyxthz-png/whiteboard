#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文案智能分句器
将用户输入的文案使用 AI 进行语义分句，输出句子列表 JSON
注意：不生成时间轴，时间轴由 TTS 实际时长决定
"""

import os
import sys
import argparse
import json
import configparser
from datetime import timedelta
from anthropic import Anthropic


def load_config(config_path):
    """加载配置文件"""
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    return config


def split_text_with_ai(text, api_key, min_chars=8, max_chars=30):
    """使用 Claude AI 进行语义分句"""
    client = Anthropic(api_key=api_key)

    prompt = f"""请将以下文案按语义分成适合朗读的句子。

要求：
1. 每句话 {min_chars}-{max_chars} 个字
2. 保持语义完整，不要在关键词中间断句
3. 适合口语朗读的节奏
4. 返回 JSON 数组格式，每个元素是一个句子字符串

文案：
{text}

请直接返回 JSON 数组，不要有其他说明文字。格式示例：
["第一句话", "第二句话", "第三句话"]
"""

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # 提取 JSON（可能被包裹在代码块中）
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        sentences = json.loads(response_text)
        return sentences

    except Exception as e:
        print(f"[ERROR] AI 分句失败: {e}", file=sys.stderr)
        # 降级方案：简单按标点分句
        return simple_split(text)


def simple_split(text):
    """简单分句（降级方案）"""
    import re
    # 按句号、问号、感叹号分句
    sentences = re.split(r'[。！？\n]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def calculate_duration(text, speed=4.0):
    """计算句子朗读时长（秒）"""
    char_count = len(text)
    duration = char_count / speed
    return duration


def format_timestamp(seconds):
    """格式化为 SRT 时间戳格式 HH:MM:SS,mmm"""
    td = timedelta(seconds=seconds)
    hours = int(td.total_seconds() // 3600)
    minutes = int((td.total_seconds() % 3600) // 60)
    secs = int(td.total_seconds() % 60)
    millis = int((td.total_seconds() % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(sentences, speed=4.0, pause=0.5):
    """生成 SRT 字幕内容"""
    srt_lines = []
    current_time = 0.0

    for idx, sentence in enumerate(sentences, start=1):
        start_time = current_time
        duration = calculate_duration(sentence, speed)
        end_time = start_time + duration

        # SRT 格式
        srt_lines.append(str(idx))
        srt_lines.append(f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}")
        srt_lines.append(sentence)
        srt_lines.append("")  # 空行分隔

        # 更新时间（加上句间停顿）
        current_time = end_time + pause

    return "\n".join(srt_lines), current_time - pause  # 返回内容和总时长


def main():
    parser = argparse.ArgumentParser(description="文案智能分句器")
    parser.add_argument("--input", required=True, help="输入文案文件路径")
    parser.add_argument("--output", help="输出句子列表 JSON 文件路径（默认：输入文件同目录）")
    parser.add_argument("--config", default="../config/config.ini", help="配置文件路径")

    args = parser.parse_args()

    # 加载配置
    config_path = os.path.join(os.path.dirname(__file__), args.config)
    config = load_config(config_path)

    # 获取参数
    min_chars = config.getint('TextToSRT', 'min_chars', fallback=8)
    max_chars = config.getint('TextToSRT', 'max_chars', fallback=30)
    claude_api_key = config.get('Claude', 'api_key', fallback='')

    # 读取文案
    if not os.path.exists(args.input):
        print(f"[ERROR] 文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input, 'r', encoding='utf-8') as f:
        text = f.read().strip()

    if not text:
        print("[ERROR] 文案内容为空", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 读取文案: {len(text)} 字")

    # AI 分句
    print("[INFO] AI 语义分句中...")
    if claude_api_key and claude_api_key != 'your_claude_api_key_here':
        sentences = split_text_with_ai(text, claude_api_key, min_chars, max_chars)
    else:
        print("[WARN] 未配置 Claude API Key，使用简单分句", file=sys.stderr)
        sentences = simple_split(text)

    print(f"[SUCCESS] 分句完成: {len(sentences)} 句")
    for i, s in enumerate(sentences, 1):
        print(f"  {i}. {s}")

    # 输出文件
    if args.output:
        output_path = args.output
    else:
        input_dir = os.path.dirname(os.path.abspath(args.input))
        input_name = os.path.splitext(os.path.basename(args.input))[0]
        output_path = os.path.join(input_dir, f"{input_name}_sentences.json")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sentences, f, ensure_ascii=False, indent=2)

    print(f"\n[SUCCESS] 分句完成!")
    print(f"[INFO] 输出文件: {output_path}")
    print(f"[INFO] 句子数量: {len(sentences)}")

    # 输出 JSON 结果（供主脚本调用）
    result = {
        "sentences_path": os.path.abspath(output_path),
        "sentence_count": len(sentences)
    }
    print(f"\nRESULT_JSON={json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
