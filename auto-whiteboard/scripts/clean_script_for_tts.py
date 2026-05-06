#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文案清洗模块 - 为TTS配音准备干净的文稿
使用Claude API清除多余符号、特殊字符，优化口语化表达
"""

import sys
import os
import json
import re
import configparser
from anthropic import Anthropic

# Windows UTF-8 输出设置
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def load_config(config_path):
    """加载配置文件"""
    config = configparser.ConfigParser()

    if not os.path.exists(config_path):
        print(f"[ERROR] 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    files_read = config.read(config_path, encoding='utf-8-sig')
    if not files_read:
        print(f"[ERROR] 无法读取配置文件: {config_path}", file=sys.stderr)
        sys.exit(1)

    return config


def clean_text_with_llm(text, api_key, base_url=None):
    """
    使用Claude API清洗文案
    - 移除Markdown符号（**、#、>等）
    - 移除多余标点符号
    - 优化口语化表达
    - 保持语义完整
    """
    if base_url:
        client = Anthropic(api_key=api_key, base_url=base_url)
    else:
        client = Anthropic(api_key=api_key)

    prompt = f"""请将以下文案清洗为适合TTS配音的纯文本：

要求：
1. 移除所有Markdown格式符号（**、#、>、-、*等）
2. 移除多余的标点符号和特殊字符
3. 保持语义完整，优化口语化表达
4. 数字和专业术语保持原样
5. 只输出清洗后的文本，不要添加任何解释

原文案：
{text}

清洗后的文本："""

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        cleaned = message.content[0].text.strip()
        return cleaned

    except Exception as e:
        print(f"[WARN] LLM清洗失败: {e}", file=sys.stderr)
        # 降级到正则清洗
        return clean_text_with_regex(text)


def clean_text_with_regex(text):
    """
    正则表达式清洗（降级方案）
    """
    # 移除Markdown加粗
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)

    # 移除Markdown标题符号
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)

    # 移除引用符号
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)

    # 移除列表符号
    text = re.sub(r'^[-*]\s+', '', text, flags=re.MULTILINE)

    # 移除多余空格
    text = re.sub(r'\s+', ' ', text)

    # 移除首尾空格
    text = text.strip()

    return text


def clean_sentences(sentences, config):
    """
    批量清洗句子列表
    """
    # 获取Claude API Key
    api_key = config.get('Claude', 'api_key', fallback=None)
    base_url = config.get('Claude', 'base_url', fallback=None)

    if not api_key or api_key == 'your_claude_api_key_here':
        print("[WARN] 未配置Claude API Key，使用正则清洗", file=sys.stderr)
        use_llm = False
    else:
        use_llm = True
        print(f"[INFO] 使用Claude API清洗文案", file=sys.stderr)

    cleaned_sentences = []

    for idx, sentence in enumerate(sentences, start=1):
        # 处理字典格式
        if isinstance(sentence, dict):
            original_text = sentence.get('text', '')
        else:
            original_text = sentence

        print(f"[{idx}/{len(sentences)}] 清洗中...", file=sys.stderr)

        # 清洗文本
        if use_llm:
            cleaned_text = clean_text_with_llm(original_text, api_key, base_url)
        else:
            cleaned_text = clean_text_with_regex(original_text)

        # 保持原格式
        if isinstance(sentence, dict):
            cleaned_sentence = sentence.copy()
            cleaned_sentence['text'] = cleaned_text
            cleaned_sentence['original_text'] = original_text  # 保留原文
        else:
            cleaned_sentence = cleaned_text

        cleaned_sentences.append(cleaned_sentence)

        print(f"    原文: {original_text[:50]}...", file=sys.stderr)
        print(f"    清洗: {cleaned_text[:50]}...", file=sys.stderr)

    return cleaned_sentences


def main():
    import argparse

    parser = argparse.ArgumentParser(description='清洗TTS文案')
    parser.add_argument('--input', required=True, help='输入JSON文件（句子列表）')
    parser.add_argument('--output', required=True, help='输出JSON文件（清洗后）')
    parser.add_argument('--config', default='config/config.ini', help='配置文件路径')

    args = parser.parse_args()

    # 加载配置
    if os.path.isabs(args.config):
        config_path = args.config
    else:
        project_root = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(project_root, args.config)

    config = load_config(config_path)

    # 读取输入
    print(f"[INFO] 读取文案: {args.input}", file=sys.stderr)
    with open(args.input, 'r', encoding='utf-8') as f:
        sentences = json.load(f)

    print(f"[INFO] 共 {len(sentences)} 句", file=sys.stderr)

    # 清洗文案
    cleaned_sentences = clean_sentences(sentences, config)

    # 保存输出
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(cleaned_sentences, f, ensure_ascii=False, indent=2)

    print(f"[SUCCESS] 清洗完成: {args.output}", file=sys.stderr)
    print(f"RESULT_JSON={json.dumps({'cleaned_count': len(cleaned_sentences), 'output_path': os.path.abspath(args.output)})}")


if __name__ == '__main__':
    main()
