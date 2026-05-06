#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频合成器
将视频、字幕、音频合成为最终成品视频
使用 ffmpeg 进行字幕烧录和音频合成
"""

import os
import sys
import argparse
import json
import configparser
import subprocess
import shutil


def load_config(config_path):
    """加载配置文件"""
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    return config


def check_ffmpeg():
    """检查 ffmpeg 是否可用"""
    if shutil.which('ffmpeg') is None:
        print("[ERROR] 未找到 ffmpeg，请先安装:", file=sys.stderr)
        print("   Windows: choco install ffmpeg", file=sys.stderr)
        print("   macOS: brew install ffmpeg", file=sys.stderr)
        print("   Linux: apt-get install ffmpeg", file=sys.stderr)
        sys.exit(1)


def srt_to_ass(srt_path, ass_path, config):
    """
    将 SRT 转换为 ASS 格式（支持样式）
    """
    print(f"\n[INFO] Converting subtitle format: SRT → ASS")

    # 读取 SRT
    with open(srt_path, 'r', encoding='utf-8') as f:
        srt_content = f.read()

    # 解析 SRT
    import re
    pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)'
    matches = re.findall(pattern, srt_content, re.DOTALL)

    # 获取字幕样式配置
    font = config.get('Subtitle', 'font', fallback='Microsoft YaHei')
    font_size = config.getint('Subtitle', 'font_size', fallback=48)
    primary_color = config.get('Subtitle', 'primary_color', fallback='&H00FFFFFF')
    outline_color = config.get('Subtitle', 'outline_color', fallback='&H00000000')
    back_color = config.get('Subtitle', 'back_color', fallback='&H80000000')
    outline_width = config.getint('Subtitle', 'outline_width', fallback=3)
    shadow = config.getint('Subtitle', 'shadow', fallback=2)
    alignment = config.getint('Subtitle', 'alignment', fallback=2)
    margin_bottom = config.getint('Subtitle', 'margin_bottom', fallback=40)
    margin_lr = config.getint('Subtitle', 'margin_lr', fallback=20)

    # 创建 ASS 文件
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary_color},&H000000FF,{outline_color},{back_color},-1,0,0,0,100,100,0,0,1,{outline_width},{shadow},{alignment},{margin_lr},{margin_lr},{margin_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    ass_events = []
    for idx, start, end, text in matches:
        # 转换时间格式：SRT (00:00:00,000) → ASS (0:00:00.00)
        start_ass = start.replace(',', '.')[:-1]  # 去掉最后一位毫秒
        end_ass = end.replace(',', '.')[:-1]

        # 移除前导零
        start_ass = start_ass.lstrip('0').lstrip(':') or '0:00:00.00'
        end_ass = end_ass.lstrip('0').lstrip(':') or '0:00:00.00'

        # 清理文本
        text = text.strip().replace('\n', '\\N')

        ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}")

    ass_content = ass_header + '\n'.join(ass_events)

    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

    print(f"  [OK] ASS 字幕: {ass_path}")


def compose_video(video_path, srt_path, audio_path, output_path, config):
    """
    合成视频：烧录字幕 + 替换音频
    """
    print(f"\n[STORYBOARD] 视频合成中...")

    # 创建临时 ASS 文件
    temp_dir = os.path.dirname(output_path)
    ass_path = os.path.join(temp_dir, 'temp_subtitles.ass')
    srt_to_ass(srt_path, ass_path, config)

    # 获取视频编码配置
    codec = config.get('Video', 'codec', fallback='libx264')
    crf = config.getint('Video', 'crf', fallback=23)
    preset = config.get('Video', 'preset', fallback='medium')
    audio_codec = config.get('Video', 'audio_codec', fallback='aac')
    audio_bitrate = config.get('Video', 'audio_bitrate', fallback='192k')

    # 构建 ffmpeg 命令
    # 注意：Windows 路径需要转义
    ass_path_escaped = ass_path.replace('\\', '/').replace(':', '\\:')

    cmd = [
        'ffmpeg',
        '-i', video_path,           # 输入视频
        '-i', audio_path,            # 输入音频
        '-vf', f"ass='{ass_path_escaped}'",  # 烧录字幕
        '-c:v', codec,               # 视频编码
        '-preset', preset,           # 编码预设
        '-crf', str(crf),            # 视频质量
        '-c:a', audio_codec,         # 音频编码
        '-b:a', audio_bitrate,       # 音频比特率
        '-map', '0:v',               # 使用第一个输入的视频
        '-map', '1:a',               # 使用第二个输入的音频
        '-y',                        # 覆盖输出文件
        output_path
    ]

    print(f"  [CONFIG] ffmpeg 参数:")
    print(f"     视频编码: {codec}, CRF: {crf}, 预设: {preset}")
    print(f"     音频编码: {audio_codec}, 比特率: {audio_bitrate}")

    # 执行 ffmpeg
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode != 0:
            print(f"[ERROR] ffmpeg 执行失败:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"[ERROR] 执行 ffmpeg 时出错: {e}", file=sys.stderr)
        sys.exit(1)

    # 清理临时文件
    if os.path.exists(ass_path):
        os.remove(ass_path)

    # 获取输出文件信息
    file_size = os.path.getsize(output_path) / (1024 * 1024)

    print(f"\n[OK] 视频合成完成!")
    print(f"  [OUTPUT] 输出: {output_path}")
    print(f"  [INFO] 大小: {file_size:.2f} MB")

    return file_size


def main():
    parser = argparse.ArgumentParser(description="视频合成器（字幕烧录 + 音频合成）")
    parser.add_argument("--video", required=True, help="输入视频文件路径")
    parser.add_argument("--srt", required=True, help="SRT 字幕文件路径")
    parser.add_argument("--audio", required=True, help="音频文件路径")
    parser.add_argument("--output", required=True, help="输出视频文件路径")
    parser.add_argument("--config", default="../config/config.ini", help="配置文件路径")

    args = parser.parse_args()

    # 检查 ffmpeg
    check_ffmpeg()

    # 检查输入文件
    for file_path, name in [(args.video, "视频"), (args.srt, "字幕"), (args.audio, "音频")]:
        if not os.path.exists(file_path):
            print(f"[ERROR] {name}文件不存在: {file_path}", file=sys.stderr)
            sys.exit(1)

    # 加载配置
    config_path = os.path.join(os.path.dirname(__file__), args.config)
    config = load_config(config_path)

    # 创建输出目录
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # 合成视频
    file_size = compose_video(args.video, args.srt, args.audio, args.output, config)

    # 输出 JSON 结果
    result = {
        "final_video_path": os.path.abspath(args.output),
        "size_mb": file_size
    }
    print(f"\nRESULT_JSON={json.dumps(result, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
