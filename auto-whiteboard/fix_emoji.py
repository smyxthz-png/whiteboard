#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re

def remove_all_emoji(text):
    """移除所有 emoji 和特殊 Unicode 字符"""
    # 移除所有 emoji 范围的字符
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002600-\U000027BF"  # misc symbols
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U00002300-\U000023FF"  # misc technical
        "\U0001FA00-\U0001FAFF"  # extended symbols
        "\U0000FE00-\U0000FE0F"  # variation selectors
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub('[EMOJI]', text)

scripts_dir = 'scripts'
for filename in os.listdir(scripts_dir):
    if filename.endswith('.py'):
        filepath = os.path.join(scripts_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            new_content = remove_all_emoji(content)

            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"[OK] {filename}")
        except Exception as e:
            print(f"[ERROR] {filename}: {e}")

print("\n[DONE] All emoji removed")
