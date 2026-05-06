#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能 TTS 参数优化器
根据句子特征动态调整 TTS 参数，使配音更自然
"""

import re


def analyze_sentence(text):
    """
    分析句子特征

    返回：{
        'type': 'question' | 'exclamation' | 'statement',
        'length': int,
        'has_pause': bool,  # 是否需要中间停顿
        'emphasis': list    # 需要强调的词
    }
    """
    analysis = {
        'type': 'statement',
        'length': len(text),
        'has_pause': False,
        'emphasis': []
    }

    # 判断句子类型
    if '？' in text or '?' in text:
        analysis['type'] = 'question'
    elif '！' in text or '!' in text:
        analysis['type'] = 'exclamation'

    # 判断是否需要中间停顿（长句）
    if len(text) > 25:
        analysis['has_pause'] = True

    # 识别需要强调的词（数字、专有名词等）
    # 数字
    numbers = re.findall(r'\d+', text)
    analysis['emphasis'].extend(numbers)

    # 引号内容
    quotes = re.findall(r'[「『""](.+?)[」』""]', text)
    analysis['emphasis'].extend(quotes)

    return analysis


def get_tts_params(text, base_tone='自然'):
    """
    根据句子特征生成 TTS 参数

    返回：{
        'tone': str,        # 语气
        'speed': float,     # 语速倍率（1.0 = 正常）
        'pause_after': float  # 句后停顿（秒）
    }
    """
    analysis = analyze_sentence(text)

    params = {
        'tone': base_tone,
        'speed': 1.0,
        'pause_after': 0.5
    }

    # 根据句子类型调整
    if analysis['type'] == 'question':
        params['speed'] = 0.95  # 稍慢
        params['pause_after'] = 0.6  # 停顿稍长
        params['tone'] = '疑问'

    elif analysis['type'] == 'exclamation':
        params['speed'] = 1.05  # 稍快
        params['pause_after'] = 0.4  # 停顿稍短
        params['tone'] = '激动'

    # 根据长度调整
    if analysis['length'] > 30:
        params['speed'] = 0.9  # 长句放慢
        params['pause_after'] = 0.7

    elif analysis['length'] < 10:
        params['speed'] = 1.1  # 短句稍快
        params['pause_after'] = 0.3

    return params


def optimize_sentence_for_tts(text):
    """
    优化句子以获得更好的 TTS 效果

    例如：
    - 添加停顿标记
    - 数字转中文
    - 添加重音标记
    """
    # 在逗号、顿号后添加短停顿
    text = text.replace('，', '，[pause:200ms]')
    text = text.replace('、', '、[pause:150ms]')

    # 在长句中间添加呼吸停顿
    if len(text) > 30:
        # 在"的"、"了"、"着"后添加微停顿
        text = re.sub(r'(的|了|着)([^，。！？])', r'\1[pause:100ms]\2', text)

    return text


# 使用示例
if __name__ == "__main__":
    test_sentences = [
        "欢迎来到我的频道。",
        "你知道这是为什么吗？",
        "太棒了！",
        "今天我们要讲解一个非常重要的概念，这个概念将会彻底改变你对世界的看法。"
    ]

    for sentence in test_sentences:
        print(f"\n句子: {sentence}")
        analysis = analyze_sentence(sentence)
        print(f"分析: {analysis}")
        params = get_tts_params(sentence)
        print(f"参数: {params}")
        optimized = optimize_sentence_for_tts(sentence)
        print(f"优化: {optimized}")
