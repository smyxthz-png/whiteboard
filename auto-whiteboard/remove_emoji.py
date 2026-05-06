#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量移除所有脚本中的 emoji 字符"""

import os
import re

# emoji 替换映射
EMOJI_MAP = {
    '🎵': '[AUDIO]',
    '🎙️': '[MIC]',
    '🎶': '[MUSIC]',
    '🔧': '[CONFIG]',
    '🔉': '[VOLUME]',
    '✨': '[EFFECT]',
    '🎚️': '[MIXER]',
    '💾': '[SAVE]',
    '✅': '[OK]',
    '🔍': '[CHECK]',
    '📁': '[MKDIR]',
    '🎬': '[STORYBOARD]',
    '🎨': '[IMAGE]',
    '🎥': '[VIDEO]',
    '🔗': '[MERGE]',
    '📹': '[OUTPUT]',
    '⚠️': '[WARN]',
    '❌': '[ERROR]',
}

def remove_emoji_from_file(filepath):
    """从文件中移除 emoji"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original = content

        # 替换已知的 emoji
        for emoji, replacement in EMOJI_MAP.items():
            content = content.replace(emoji, replacement)

        # 移除所有其他 emoji (Unicode 范围)
        # Emoji 主要在这些范围: U+1F300-U+1F9FF, U+2600-U+26FF, U+2700-U+27BF
        content = re.sub(r'[\U0001F300-\U0001F9FF\U00002600-\U000027BF]+', '[EMOJI]', content)

        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[OK] {os.path.basename(filepath)}")
            return True
        return False
    except Exception as e:
        print(f"[ERROR] {filepath}: {e}")
        return False

def main():
    scripts_dir = 'scripts'
    count = 0

    for filename in os.listdir(scripts_dir):
        if filename.endswith('.py'):
            filepath = os.path.join(scripts_dir, filename)
            if remove_emoji_from_file(filepath):
                count += 1

    print(f"\n处理完成: {count} 个文件已更新")

if __name__ == '__main__':
    main()
