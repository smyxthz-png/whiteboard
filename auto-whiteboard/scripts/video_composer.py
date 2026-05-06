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
import re


def load_config(config_path):
    """加载配置文件"""
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8-sig')
    return config


def check_ffmpeg():
    """检查 ffmpeg 是否可用"""
    if shutil.which('ffmpeg') is None:
        print("[ERROR] 未找到 ffmpeg，请先安装:", file=sys.stderr)
        print("   Windows: choco install ffmpeg", file=sys.stderr)
        print("   macOS: brew install ffmpeg", file=sys.stderr)
        print("   Linux: apt-get install ffmpeg", file=sys.stderr)
        sys.exit(1)


def probe_media(path):
    """读取媒体尺寸和时长。"""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_streams',
        '-show_format',
        '-of', 'json',
        path
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        check=True
    )
    data = json.loads(result.stdout)
    streams = data.get('streams', [])
    video_stream = next((s for s in streams if s.get('codec_type') == 'video'), {})
    duration = float(data.get('format', {}).get('duration') or 0)
    return {
        'width': int(video_stream.get('width') or 1920),
        'height': int(video_stream.get('height') or 1080),
        'duration': duration,
    }


def parse_srt_timestamp(timestamp):
    """SRT 时间戳转秒。"""
    match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', timestamp)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {timestamp}")
    hours, minutes, seconds, millis = match.groups()
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis) / 1000.0
    )


def format_ass_timestamp(seconds):
    """秒转 ASS 时间戳 H:MM:SS.cc。"""
    seconds = max(0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        secs += 1
        centis -= 100
    if secs >= 60:
        minutes += 1
        secs -= 60
    if minutes >= 60:
        hours += 1
        minutes -= 60
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def split_subtitle_text(text, max_chars):
    """把字幕文本拆成多个单行事件。"""
    text = re.sub(r'\s+', ' ', text.strip())
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = ''
    tokens = re.findall(r'.+?[，,、；;：:]|.+$', text)

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        while len(token) > max_chars:
            if current:
                chunks.append(current)
                current = ''
            chunks.append(token[:max_chars])
            token = token[max_chars:]
        if not token:
            continue
        if len(current) + len(token) <= max_chars:
            current += token
        else:
            if current:
                chunks.append(current)
            current = token

    if current:
        chunks.append(current)
    return chunks


def escape_ass_text(text):
    """避免字幕内容被 ASS override 解析。"""
    return text.replace('{', '(').replace('}', ')').replace('\n', ' ')


def srt_to_ass(srt_path, ass_path, config, video_width=1920, video_height=1080):
    """
    将 SRT 转换为 ASS 格式（支持样式）
    """
    print(f"\n[INFO] Converting subtitle format: SRT → ASS")

    # 读取 SRT
    with open(srt_path, 'r', encoding='utf-8') as f:
        srt_content = f.read()

    # 解析 SRT
    pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)'
    matches = re.findall(pattern, srt_content, re.DOTALL)

    # 获取字幕样式配置
    font = config.get('Subtitle', 'font', fallback='Microsoft YaHei')
    font_size = config.getint('Subtitle', 'font_size', fallback=40)
    primary_color = config.get('Subtitle', 'primary_color', fallback='&H00FFFFFF')
    outline_color = config.get('Subtitle', 'outline_color', fallback='&H00000000')
    back_color = config.get('Subtitle', 'back_color', fallback='&H80000000')
    outline_width = config.getint('Subtitle', 'outline_width', fallback=2)
    shadow = config.getint('Subtitle', 'shadow', fallback=2)
    alignment = config.getint('Subtitle', 'alignment', fallback=2)
    margin_bottom = config.getint('Subtitle', 'margin_bottom', fallback=40)
    margin_lr = config.getint('Subtitle', 'margin_lr', fallback=20)
    max_chars_per_line = config.getint('Subtitle', 'max_chars_per_line', fallback=18)

    # 创建 ASS 文件
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 2
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
        start_sec = parse_srt_timestamp(start)
        end_sec = parse_srt_timestamp(end)
        duration = max(0.01, end_sec - start_sec)

        chunks = split_subtitle_text(text, max_chars_per_line)
        total_chars = max(1, sum(len(chunk) for chunk in chunks))
        cursor = start_sec

        for chunk_index, chunk in enumerate(chunks):
            if chunk_index == len(chunks) - 1:
                chunk_end = end_sec
            else:
                chunk_duration = duration * (len(chunk) / total_chars)
                chunk_end = min(end_sec, cursor + chunk_duration)

            ass_events.append(
                "Dialogue: 0,"
                f"{format_ass_timestamp(cursor)},"
                f"{format_ass_timestamp(chunk_end)},"
                f"Default,,0,0,0,,{escape_ass_text(chunk)}"
            )
            cursor = chunk_end

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

    video_info = probe_media(video_path)
    audio_info = probe_media(audio_path)
    target_duration = audio_info['duration'] or video_info['duration']
    pad_duration = max(0.0, target_duration - video_info['duration'])

    srt_to_ass(srt_path, ass_path, config, video_info['width'], video_info['height'])

    # 获取视频编码配置
    codec = config.get('Video', 'codec', fallback='libx264')
    crf = config.getint('Video', 'crf', fallback=23)
    preset = config.get('Video', 'preset', fallback='medium')
    audio_codec = config.get('Video', 'audio_codec', fallback='aac')
    audio_bitrate = config.get('Video', 'audio_bitrate', fallback='192k')

    # 构建 ffmpeg 命令
    # 注意：Windows 路径需要转义
    ass_path_escaped = ass_path.replace('\\', '/').replace(':', '\\:')

    video_filter = (
        f"[0:v]tpad=stop_mode=clone:stop_duration={pad_duration:.3f},"
        f"trim=duration={target_duration:.3f},"
        f"setpts=PTS-STARTPTS,"
        f"ass='{ass_path_escaped}'[v]"
    )

    cmd = [
        'ffmpeg',
        '-i', video_path,           # 输入视频
        '-i', audio_path,            # 输入音频
        '-filter_complex', video_filter,
        '-c:v', codec,               # 视频编码
        '-preset', preset,           # 编码预设
        '-crf', str(crf),            # 视频质量
        '-c:a', audio_codec,         # 音频编码
        '-b:a', audio_bitrate,       # 音频比特率
        '-map', '[v]',               # 使用校准后的字幕视频
        '-map', '1:a',               # 使用第二个输入的音频
        '-y',                        # 覆盖输出文件
        output_path
    ]

    print(f"  [CONFIG] ffmpeg 参数:")
    print(f"     视频编码: {codec}, CRF: {crf}, 预设: {preset}")
    print(f"     音频编码: {audio_codec}, 比特率: {audio_bitrate}")
    print(f"     视频尺寸: {video_info['width']}x{video_info['height']}")
    print(f"     时长校准: video={video_info['duration']:.3f}s, audio={target_duration:.3f}s, pad={pad_duration:.3f}s")

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
