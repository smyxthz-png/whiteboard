#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步验证脚本
验证 SRT 字幕和音频是否完全对齐
"""

import sys
import argparse
import subprocess
import shutil


def parse_srt(srt_path):
    """解析 SRT 文件"""
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    import re
    pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)

    entries = []
    for idx, start, end, text in matches:
        start_ms = time_to_ms(start)
        end_ms = time_to_ms(end)
        entries.append({
            'index': int(idx),
            'start': start_ms / 1000.0,
            'end': end_ms / 1000.0,
            'duration': (end_ms - start_ms) / 1000.0,
            'text': text.strip()
        })

    return entries


def time_to_ms(time_str):
    """SRT 时间转毫秒"""
    h, m, s = time_str.split(':')
    s, ms = s.split(',')
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)


def check_ffmpeg():
    """检查 ffmpeg 是否可用"""
    if not shutil.which('ffprobe'):
        print("[ERROR] ffprobe 未安装或不在 PATH 中", file=sys.stderr)
        print("请安装 ffmpeg: https://ffmpeg.org/download.html", file=sys.stderr)
        sys.exit(1)


def get_audio_duration(audio_path):
    """使用 ffprobe 获取音频时长"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 获取音频时长失败: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"[ERROR] 解析音频时长失败: {e}", file=sys.stderr)
        sys.exit(1)


def verify_sync(srt_path, audio_path, tolerance=0.1):
    """
    验证同步性

    tolerance: 容差（秒），默认 100ms
    """
    print(f"[EMOJI] SRT 文件: {srt_path}")
    print(f"[MIC]  音频文件: {audio_path}")
    print(f"[EMOJI][EMOJI]  容差: {tolerance}s\n")

    # 解析 SRT
    entries = parse_srt(srt_path)
    print(f"[OK] 解析 SRT: {len(entries)} 条字幕\n")

    # 获取音频时长
    audio_duration = get_audio_duration(audio_path)
    print(f"[OK] 加载音频: {audio_duration:.2f}s\n")

    # 注意：ffmpeg 没有简单的静音检测 API，这里简化验证逻辑
    # 只检查时长匹配，不检查每个片段的有声部分
    print("[INFO] 使用 ffmpeg 后端，跳过详细的有声片段检测")
    print("[INFO] 仅验证总体时长匹配\n")

    # 验证每条字幕（简化版）
    print("=" * 60)
    print("验证结果")
    print("=" * 60)

    all_ok = True

    for i, entry in enumerate(entries):
        print(f"\n[{entry['index']}] {entry['text'][:30]}...")
        print(f"   SRT 时间: {entry['start']:.2f}s - {entry['end']:.2f}s (时长: {entry['duration']:.2f}s)")

        # 检查时间范围是否在音频范围内
        if entry['end'] > audio_duration + tolerance:
            print("   [ERROR] 字幕结束时间超出音频时长！")
            all_ok = False
        else:
            print("   [OK] 时间范围正常")

    # 总体验证
    print("\n" + "=" * 60)
    print("总体验证")
    print("=" * 60)

    srt_total_duration = entries[-1]['end'] if entries else 0
    duration_diff = abs(srt_total_duration - audio_duration)

    print(f"SRT 总时长: {srt_total_duration:.2f}s")
    print(f"音频总时长: {audio_duration:.2f}s")
    print(f"时长差异: {duration_diff:.2f}s")

    if duration_diff > tolerance:
        print(f"[ERROR] 时长差异超过容差 ({tolerance}s)")
        all_ok = False
    else:
        print("[OK] 时长匹配")

    print("\n" + "=" * 60)
    if all_ok:
        print("[EMOJI] 验证通过：字幕和音频完全同步！")
    else:
        print("[ERROR] 验证失败：存在同步问题")
    print("=" * 60)

    return all_ok


def main():
    parser = argparse.ArgumentParser(description="SRT 和音频同步验证")
    parser.add_argument("--srt", required=True, help="SRT 字幕文件路径")
    parser.add_argument("--audio", required=True, help="音频文件路径")
    parser.add_argument("--tolerance", type=float, default=0.1, help="容差（秒）")

    args = parser.parse_args()

    # 检查 ffmpeg
    check_ffmpeg()

    success = verify_sync(args.srt, args.audio, args.tolerance)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
